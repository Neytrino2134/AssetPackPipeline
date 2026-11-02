"""Human-facing presets and ordered operations; uses the same API as MCP."""
import copy
import re
from pathlib import Path


def prepare(base, source, pack, fmt, variants='both', renders=(), lod=0, finalize=False, output='', view_modes=()):
    from . import render_views
    view_modes=render_views.settings(view_modes)
    if not Path(source).is_dir():
        raise ValueError('Выберите существующую папку исходников.')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', pack):
        raise ValueError('Имя пака: латинские буквы, цифры и подчёркивание; первая буква латинская.')
    if fmt not in ('FBX', 'GLB') or variants not in ('both', 'LOD', 'Nanite'):
        raise ValueError('Неверный формат или состав мешей.')
    if set(renders)-{'overview', 'MID', 'LOW', 'LODS', 'selected'}:
        raise ValueError('Неизвестный режим рендера.')
    if isinstance(lod, bool) or not isinstance(lod, int) or not 0 <= lod < len(base['lod_screen_sizes']):
        raise ValueError('Выбранный LOD отсутствует в настройках профиля.')
    if 'MID' in renders and variants == 'LOD':
        raise ValueError('Для рендера MID включите Nanite.')
    if set(renders)&{'LOW', 'LODS', 'selected'} and variants == 'Nanite':
        raise ValueError('Для рендера LOW/LOD включите версию LOD.')
    profiles = {}
    if output and not Path(output).is_absolute():
        raise ValueError('Каталог вывода должен быть абсолютным.')
    for variant in ('LOD', 'Nanite') if variants == 'both' else (variants,):
        p = copy.deepcopy(base)
        p.update(pack_id=pack, source_root=str(Path(source).resolve()), source_format=fmt,
                 destination_root='/Game/'+pack, mesh_subdirectory=variant,
                 nanite_enabled=variant == 'Nanite', nanite_source='AUTO', validation_policy='warn',
                 texture_directory=fmt+'/Textures', asset_overrides={}, skip_invalid_sources=False)
        p['overview'] = dict(p.get('overview', {}), map_name='Overview_'+pack+'_'+variant)
        p['overview'].pop('map_path_override', None)
        p.pop('asset_ids', None)
        p['previews'] = dict(p.get('previews', {}), mode='overview', camera='overview',view_modes=view_modes)
        p['delivery'] = dict(p.get('delivery', {}), maps='overview', output_directory=output)
        indices = sorted(({0} if 'LOW' in renders else set()) |
                         (set(range(len(p['lod_screen_sizes']))) if 'LODS' in renders else set()) |
                         ({lod} if 'selected' in renders else set())) if variant == 'LOD' else [0]
        p['media'] = dict(p.get('media', {}), yaw_angles=[90], lod_index=0, lod_indices=indices or [0])
        profiles[variant] = p
    steps = []
    for variant in profiles:
        steps.extend([(variant, 'import'), (variant, 'validate'), (variant, 'overview')])
    if 'overview' in renders:
        steps.append(('LOD' if 'LOD' in profiles else 'Nanite', 'preview'))
    if 'LOD' in profiles and set(renders)&{'LOW', 'LODS', 'selected'}:
        steps.append(('LOD', 'media'))
    if 'Nanite' in profiles and 'MID' in renders:
        steps.append(('Nanite', 'media'))
    if finalize:
        steps.extend([(next(iter(profiles)), op) for op in ('delivery', 'verify_delivery', 'package')])
    return profiles, steps


RENDER_OPERATIONS = ('overview', 'preview', 'media')


def render_steps(steps):
    """Stage 4 'render only': image jobs of an already imported pack, then export."""
    renders = [s for s in steps if s[1] in RENDER_OPERATIONS]
    if not any(op in ('preview', 'media') for _, op in renders):
        raise ValueError('В разделе «3. Изображения» не выбран ни один рендер.')
    # The overview scene is only needed by the overview preview.
    keep = {v for v, op in renders if op == 'preview'}
    renders = [(v, op) for v, op in renders if op != 'overview' or v in keep]
    return renders+[(renders[-1][0], 'export_renders')]


def export_final_renders(reports, profile_path):
    """Copy finished PNGs to FinalProject/<timestamp>/<pack>_Renders(.zip)."""
    from .discovery import read_json
    from .final_output import export_renders, export_root
    if not reports:
        raise RuntimeError('Рендеры не созданы.')
    profile = read_json(profile_path)
    output = profile.get('delivery', {}).get('output_directory', '')
    base = Path(output) if output else Path(reports[0]['output_directory']).resolve().parents[1]/'RenderExports'
    return export_renders(reports, export_root(base), profile['pack_id'])


class Session:
    """Advance only after a successful job. Cancel never launches later steps."""
    def __init__(self, api, paths, steps):
        self.api, self.paths, self.steps = api, paths, list(steps)
        self.waiting = None
        self.done = False
        self.error = None
        self.label = 'Подготовка'
        self.delivery_id = None
        self.render_runs = []
        self.result = None

    def cancel(self):
        self.steps.clear()
        self.done = True
        self.label = 'Остановлено пользователем'
        if self.waiting:
            self.api.cancel(self.waiting)

    def tick(self):
        if getattr(self,'_advancing',False):
            return
        self._advancing = True
        try:
            self._advance()
        finally:
            self._advancing = False

    def _advance(self):
        if self.done:
            return
        try:
            if self.waiting:
                report = self.api.status(self.waiting)
                state = report['status']
                if state == 'running':
                    return
                self.waiting = None
                if state != 'passed':
                    raise RuntimeError('Этап завершён со статусом '+state+'. См. отчёт; продолжение остановлено.')
                if report.get('kind') in ('preview_export', 'individual_previews'):
                    self.render_runs.append(report)
            if not self.steps:
                self.done = True
                self.label = (('Поставка готова: '+self.result['zip_path']) if self.result and 'zip_path' in self.result
                              else ('Рендеры готовы: '+self.result['renders']['zip_path']) if self.result
                              else 'Меши и сцены подготовлены.')
                return
            variant, operation = self.steps.pop(0)
            path = self.paths[variant]
            self.label = variant+' • '+operation
            if operation == 'import':
                self.waiting = self.api.start(path)
            elif operation == 'settings':
                self.waiting = self.api.start_settings(path)
            elif operation == 'validate':
                if not self.api.validate(path)['passed']:
                    raise RuntimeError('Проверка ассетов не пройдена. См. отчёт.')
            elif operation == 'overview':
                if self.api.create_overview(path)['status'] != 'passed':
                    raise RuntimeError('Обзорная сцена не создана. См. отчёт.')
            elif operation == 'preview':
                self.waiting = self.api.start_previews(path)
            elif operation == 'media':
                self.waiting = self.api.start_media(path)
            elif operation == 'delivery':
                report = self.api.create_combined_delivery(list(self.paths.values())) if len(self.paths)>1 else self.api.create_delivery(path)
                if report['status'] != 'passed':
                    raise RuntimeError('Не удалось создать чистый проект. См. отчёт поставки.')
                self.delivery_id = report['run_id']
            elif operation == 'verify_delivery':
                self.waiting = self.api.start_delivery_verification(self.delivery_id)
            elif operation == 'package':
                self.result = self.api.package_delivery(self.delivery_id)
                from .final_output import export_renders
                from .discovery import read_json
                self.result['renders'] = export_renders(self.render_runs, Path(self.result['zip_path']).parent, read_json(path)['pack_id'])
            elif operation == 'export_renders':
                self.result = {'renders': export_final_renders(self.render_runs, path)}
            else:
                raise ValueError('Неизвестная операция '+operation)
        except Exception as error:
            self.done, self.error = True, str(error)
            self.label = str(error)
