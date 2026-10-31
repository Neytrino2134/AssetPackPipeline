"""Prepare the complete catalog for review, retaining quality issues per model."""
import copy


def select(report, verify_sources, inspect_asset):
    rows = {row['id']: row for row in report['assets']}
    accepted, checks = [], []
    issues = []
    for asset in report['manifest']['assets']:
        row = rows.get(asset['id'], {})
        accepted.append(asset['id'])
        if row.get('status') not in ('passed', 'skipped') or row.get('passed') is not True:
            check = {'id': asset['id'], 'passed': False, 'preparation_passed': False,
                     'error': row.get('error') or row.get('validation_summary') or 'Import did not complete'}
            checks.append(check)
            issues.append({'id': asset['id'], 'stage': 'import', 'reason': check['error'], 'blocking': True})
            continue
        # Changed inputs invalidate the candidate, rather than silently mixing revisions.
        verify_sources(asset)
        try:
            check = inspect_asset(asset)
        except Exception as error:
            check = {'id': asset['id'], 'passed': False, 'error': str(error)}
        checks.append(check)
        if check.get('warnings') or not check.get('passed'):
            issues.append({'id': asset['id'], 'stage': 'candidate_readback',
                           'reason': check.get('error') or check.get('validation_summary') or 'Quality warnings',
                           'blocking': not check.get('passed', False), 'warnings': check.get('warnings', [])})
    return accepted, issues, checks


def profile(original, accepted):
    if not accepted:
        raise ValueError('No catalog assets available for a review candidate')
    result = copy.deepcopy(original)
    result.update(asset_ids=list(accepted))
    result.pop('skip_invalid_sources', None)
    result['asset_overrides'] = {k:v for k,v in result.get('asset_overrides', {}).items() if k in accepted}
    result.setdefault('overview', {})['require_valid_assets'] = True
    result.setdefault('media', {})['include_invalid'] = False
    if result.get('nanite_enabled'):
        result['media'].update(lod_index=0, lod_indices=[0])
        if result.setdefault('delivery', {}).get('maps') == 'both': result['delivery']['maps'] = 'overview'
        if result.setdefault('previews', {}).get('mode') in ('both', 'lod_review'): result['previews']['mode'] = 'overview'
    return result
