#include "AssetPackPipelineNative.h"
#include "Modules/ModuleManager.h"
#include "Framework/Docking/TabManager.h"
#include "Widgets/Docking/SDockTab.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SMultiLineEditableTextBox.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SComboBox.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformProcess.h"
#include "Widgets/Text/STextBlock.h"
#include "DesktopPlatformModule.h"
#include "IDesktopPlatform.h"
#include "IPythonScriptPlugin.h"
#include "Misc/Base64.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/MessageDialog.h"
#include "Serialization/JsonSerializer.h"
#include "Styling/AppStyle.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/SWindow.h"

static const FName PipelineTab(TEXT("AssetPackPipelineNative"));
static TWeakPtr<SDockTab> LivePipelineTab;
class SPipelinePanel;
static TWeakPtr<SPipelinePanel> LivePipelinePanel;

class SPipelinePanel : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SPipelinePanel) {} SLATE_END_ARGS()
    TSharedPtr<SEditableTextBox> Source, Pack, Output, SelectedLOD, Key, Chat, OverrideID;
    TSharedPtr<SComboBox<TSharedPtr<FString>>> FolderMenu, ModelMenu, RunMenu;
    TArray<TSharedPtr<FString>> Modes, Formats, Models, Folders, Runs;
    FString RunID;
    FString Mode=TEXT("Быстрый старт"), FormatValue=TEXT("FBX"), Model=TEXT("gpt-6.1-sol"), CleanupRoot;
    int32 Step=0;
    TSharedPtr<SMultiLineEditableTextBox> Advanced;
    TSharedPtr<SMultiLineEditableTextBox> ChatHistory, TaskHistory;
    TArray<TSharedPtr<FString>> Permissions;
    FString Permission=TEXT("Только советы"), LastChat, LastTasks;
    bool bAIPending=false;
    bool bShowAI=false, bShowContent=false, bShowJournal=false;
    TMap<FString,TSharedPtr<SEditableTextBox>> ProfessionalFields;
    TMap<FString,TSharedPtr<SEditableTextBox>> OverrideFields;
    bool bRawProfile=false;
    TSharedPtr<SVerticalBox> Form;
    TSharedPtr<STextBlock> Status;
    bool bMID=true, bLOD=true, bRender=true, bZip=true;
    bool bRenderMID=false, bRenderLOW=false, bRenderLODS=false, bRenderSelected=false, bRemember=false;
    FString State;
    bool Exercise(int32 Index)
    {
        Mode=*Modes[Index%Modes.Num()]; Step=Index%4;
        bShowAI=true; bShowJournal=Index%3==0;
        const FString TestText=FString::Printf(TEXT("Проверка ввода RU / EN — строка %d"),Index);
        Chat->SetText(FText::FromString(TestText));
        bMID=Index%2==0; bLOD=true; bRender=Index%3==0;
        if(ModelMenu) ModelMenu->SetIsOpen(Index%5==1,false);
        if(auto Window=FSlateApplication::Get().FindWidgetWindow(AsShared()))
            Window->Resize(FVector2D(1000+(Index%3)*100,800+(Index%2)*100));
        return Chat->GetText().ToString()==TestText;
    }
    TSharedRef<SWidget> Combo(TArray<TSharedPtr<FString>>& Items, FString& Value, TSharedPtr<SComboBox<TSharedPtr<FString>>>* Out=nullptr)
    {
        FString* Ptr=&Value;
        TSharedPtr<SComboBox<TSharedPtr<FString>>> Widget;
        SAssignNew(Widget,SComboBox<TSharedPtr<FString>>).OptionsSource(&Items)
            .OnGenerateWidget_Lambda([](TSharedPtr<FString> Item){return SNew(STextBlock).Text(FText::FromString(*Item));})
            .OnSelectionChanged_Lambda([Ptr](TSharedPtr<FString> Item,ESelectInfo::Type){if(Item.IsValid()) *Ptr=*Item;})
            [SNew(STextBlock).Text_Lambda([Ptr](){return FText::FromString(*Ptr);})];
        if(Out) *Out=Widget;
        return Widget.ToSharedRef();
    }

    void Field(const TCHAR* Label, TSharedPtr<SEditableTextBox>& Widget, const FString& Value)
    {
        Form->AddSlot().AutoHeight().Padding(0,6)[SNew(STextBlock).Text(FText::FromString(Label))];
        Form->AddSlot().AutoHeight()[SAssignNew(Widget, SEditableTextBox).Text(FText::FromString(Value))];
    }
    void Button(const TCHAR* Label, TFunction<FReply()> Callback)
    {
        Form->AddSlot().AutoHeight().Padding(0,6)[SNew(SButton).Text(FText::FromString(Label)).OnClicked_Lambda(Callback)];
    }
    void Check(const TCHAR* Label, bool& Value)
    {
        bool* Ptr=&Value;
        Form->AddSlot().AutoHeight().Padding(0,5)[SNew(SCheckBox)
            .IsChecked_Lambda([Ptr](){return *Ptr ? ECheckBoxState::Checked : ECheckBoxState::Unchecked;})
            .OnCheckStateChanged_Lambda([Ptr](ECheckBoxState V){*Ptr=V==ECheckBoxState::Checked;})
            [SNew(STextBlock).Text(FText::FromString(Label))]];
    }
    FReply Browse(TSharedPtr<SEditableTextBox> Target)
    {
        FString Selected;
        if (IDesktopPlatform* Desktop=FDesktopPlatformModule::Get())
            if (Desktop->OpenDirectoryDialog(nullptr,TEXT("Asset Pack Pipeline"),Target->GetText().ToString(),Selected))
                Target->SetText(FText::FromString(Selected));
        return FReply::Handled();
    }
    FReply Send(const FString& Action)
    {
        TSharedRef<FJsonObject> Data=MakeShared<FJsonObject>();
        Data->SetStringField(TEXT("action"),Action);
        Data->SetStringField(TEXT("source"),Source->GetText().ToString());
        Data->SetStringField(TEXT("pack"),Pack->GetText().ToString());
        Data->SetStringField(TEXT("format"),FormatValue);
        Data->SetStringField(TEXT("mode"),Mode);
        Data->SetStringField(TEXT("model"),Model);
        Data->SetStringField(TEXT("ai_permission"),Permission);
        Data->SetStringField(TEXT("chat"),Chat->GetText().ToString());
        Data->SetStringField(TEXT("cleanup_root"),CleanupRoot);
        Data->SetStringField(TEXT("run_id"),RunID);
        Data->SetStringField(TEXT("override_id"),OverrideID->GetText().ToString());
        TSharedRef<FJsonObject> Overrides=MakeShared<FJsonObject>();
        for(const auto& Pair:OverrideFields) Overrides->SetStringField(Pair.Key,Pair.Value->GetText().ToString());
        Data->SetObjectField(TEXT("override_fields"),Overrides);
        Data->SetStringField(TEXT("selected_lod"),SelectedLOD->GetText().ToString());
        Data->SetBoolField(TEXT("render_MID"),bRenderMID); Data->SetBoolField(TEXT("render_LOW"),bRenderLOW);
        Data->SetBoolField(TEXT("render_LODS"),bRenderLODS); Data->SetBoolField(TEXT("render_selected"),bRenderSelected);
        Data->SetBoolField(TEXT("remember"),bRemember);
        if(Action==TEXT("ai_save") && !Key->GetText().IsEmpty())
        {
            FPlatformMisc::SetEnvironmentVar(TEXT("OPENAI_API_KEY"),*Key->GetText().ToString());
            Key->SetText(FText::GetEmpty());
        }
        Data->SetStringField(TEXT("output"),Output->GetText().ToString());
        Data->SetStringField(TEXT("profile_json"),Advanced->GetText().ToString());
        Data->SetBoolField(TEXT("raw_profile"),bRawProfile);
        TSharedRef<FJsonObject> Fields=MakeShared<FJsonObject>();
        for(const auto& Pair:ProfessionalFields) Fields->SetStringField(Pair.Key,Pair.Value->GetText().ToString());
        Data->SetObjectField(TEXT("professional_fields"),Fields);
        Data->SetBoolField(TEXT("mid"),bMID); Data->SetBoolField(TEXT("lod"),bLOD);
        Data->SetBoolField(TEXT("render"),bRender); Data->SetBoolField(TEXT("zip"),bZip);
        FString Json;
        FJsonSerializer::Serialize(Data,TJsonWriterFactory<>::Create(&Json));
        FTCHARToUTF8 Utf8(*Json);
        FString Encoded=FBase64::Encode(reinterpret_cast<const uint8*>(Utf8.Get()),Utf8.Length());
        IPythonScriptPlugin::Get()->ExecPythonCommand(*FString::Printf(TEXT("from asset_pack_pipeline import native_bridge; native_bridge.submit_b64('%s')"),*Encoded));
        Refresh();
        return FReply::Handled();
    }
    void Refresh()
    {
        FString NewState;
        if(!FFileHelper::LoadFileToString(NewState,*(FPaths::ProjectSavedDir()/TEXT("AssetPackPipeline/Native/state.json"))) || NewState==State) return;
        State=NewState;
        TSharedPtr<FJsonObject> Data;
        if(FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(State),Data) && Data.IsValid())
        {
            FString Summary;
            if(!Data->TryGetStringField(TEXT("error"),Summary) && !Data->TryGetStringField(TEXT("stage"),Summary)
                && !Data->TryGetStringField(TEXT("ai"),Summary)) Summary=TEXT("Получено обновление. Подробности — в журнале и папке отчётов.");
            const TSharedPtr<FJsonObject>* Job;
            if(Data->TryGetObjectField(TEXT("job"),Job))
            {
                FString JobStatus;
                if((*Job)->TryGetStringField(TEXT("status"),JobStatus)) Summary=TEXT("Задача: ")+JobStatus;
            }
            const TSharedPtr<FJsonObject>* Cleanup;
            if(Data->TryGetObjectField(TEXT("cleanup_plan"),Cleanup))
                FJsonSerializer::Serialize((*Cleanup).ToSharedRef(),TJsonWriterFactory<>::Create(&Summary));
            Status->SetText(FText::FromString(Summary));
            Data->TryGetBoolField(TEXT("ai_pending"),bAIPending);
            FString LogText;
            if(Data->TryGetStringField(TEXT("chat_history"),LogText) && LogText!=LastChat && ChatHistory)
            { LastChat=LogText; ChatHistory->SetText(FText::FromString(LogText)); }
            if(Data->TryGetStringField(TEXT("task_history"),LogText) && LogText!=LastTasks && TaskHistory)
            { LastTasks=LogText; TaskHistory->SetText(FText::FromString(LogText)); }
            const TSharedPtr<FJsonObject>* Found;
            if(Data->TryGetObjectField(TEXT("override_fields"),Found))
            {
                for(const auto& Pair:(*Found)->Values)
                    if(auto* Widget=OverrideFields.Find(FString(Pair.Key))) (*Widget)->SetText(FText::FromString(Pair.Value->AsString()));
            }
            if(Data->TryGetObjectField(TEXT("professional_fields"),Found))
            {
                for(const auto& Pair:(*Found)->Values)
                    if(auto* Widget=ProfessionalFields.Find(FString(Pair.Key))) (*Widget)->SetText(FText::FromString(Pair.Value->AsString()));
            }
            if(Data->TryGetObjectField(TEXT("loaded_profile"),Found))
            {
                FString Text;
                FJsonSerializer::Serialize((*Found).ToSharedRef(),TJsonWriterFactory<>::Create(&Text));
                Advanced->SetText(FText::FromString(Text));
                FString Value;
                if((*Found)->TryGetStringField(TEXT("source_root"),Value)) Source->SetText(FText::FromString(Value));
                if((*Found)->TryGetStringField(TEXT("pack_id"),Value)) Pack->SetText(FText::FromString(Value));
                if((*Found)->TryGetStringField(TEXT("source_format"),Value)) FormatValue=Value;
            }
            if(Data->TryGetObjectField(TEXT("content_folders"),Found))
            {
                Folders.Empty();
                for(const auto& Pair:(*Found)->Values) Folders.Add(MakeShared<FString>(Pair.Key));
                if(FolderMenu) FolderMenu->RefreshOptions();
            }
            const TArray<TSharedPtr<FJsonValue>>* Values;
            if(Data->TryGetArrayField(TEXT("queue"),Values))
            {
                Runs.Empty();
                for(const auto& Value:*Values) Runs.Add(MakeShared<FString>(Value->AsObject()->GetStringField(TEXT("run_id"))));
                if(RunMenu) RunMenu->RefreshOptions();
            }
            if(Data->TryGetArrayField(TEXT("models"),Values))
            {
                Models.Empty();
                for(const auto& Value:*Values) Models.Add(MakeShared<FString>(Value->AsString()));
                if(ModelMenu) ModelMenu->RefreshOptions();
            }
        }
    }
    void Construct(const FArguments& Args)
    {
        FString Preferences;
        const FString PreferencesPath=FPaths::Combine(FPlatformMisc::GetEnvironmentVariable(TEXT("LOCALAPPDATA")),TEXT("AssetPackPipeline/ai-settings.json"));
        if(FFileHelper::LoadFileToString(Preferences,*PreferencesPath))
        {
            TSharedPtr<FJsonObject> SavedSettings;
            if(FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Preferences),SavedSettings) && SavedSettings.IsValid())
                SavedSettings->TryGetStringField(TEXT("model"),Model);
        }
        ChildSlot[SNew(SScrollBox)+SScrollBox::Slot().Padding(20)[SAssignNew(Form,SVerticalBox)]];
        Form->AddSlot().AutoHeight().Padding(0,10)[SNew(STextBlock).Text(FText::FromString(TEXT("Asset Pack Pipeline | Native Slate"))).Font(FAppStyle::GetFontStyle("HeadingExtraSmall"))];
        Form->AddSlot().AutoHeight()[SNew(STextBlock).AutoWrapText(true).Text(FText::FromString(TEXT("Быстрый старт: исходники → меши → общий кадр → проверенный ZIP. Tkinter не используется.")))];
        for(const TCHAR* Name:{TEXT("Быстрый старт"),TEXT("Мастер"),TEXT("Профессиональный")}) Modes.Add(MakeShared<FString>(Name));
        for(const TCHAR* Name:{TEXT("FBX"),TEXT("GLB")}) Formats.Add(MakeShared<FString>(Name));
        for(const TCHAR* Name:{TEXT("gpt-6.1-sol"),TEXT("gpt-6-astra"),TEXT("gpt-6.1-terra"),TEXT("gpt-6-luna")}) Models.Add(MakeShared<FString>(Name));
        Form->AddSlot().AutoHeight().Padding(0,8)[Combo(Modes,Mode)];
        Button(TEXT("Мастер: назад"),[this](){Step=FMath::Max(0,Step-1);return FReply::Handled();});
        Button(TEXT("Мастер: далее"),[this](){Step=FMath::Min(3,Step+1);return FReply::Handled();});
        TSharedPtr<SVerticalBox> Main=Form;
        auto Group=[this,Main](int32 Index){
            TSharedPtr<SVerticalBox> Body;
            Main->AddSlot().AutoHeight()[SNew(SBox).Visibility_Lambda([this,Index](){return Mode!=TEXT("Мастер") || Step==Index ? EVisibility::Visible:EVisibility::Collapsed;})[SAssignNew(Body,SVerticalBox)]];
            Form=Body;
        };
        Group(0);
        Field(TEXT("1. Папка исходников"),Source,TEXT(""));
        Button(TEXT("Выбрать исходники…"),[this](){return Browse(Source);});
        Field(TEXT("Имя пака (латиница)"),Pack,TEXT("MyAssetPack"));
        Form->AddSlot().AutoHeight().Padding(0,8)[Combo(Formats,FormatValue)];
        Group(1);
        Check(TEXT("2. LOW / LOD"),bLOD); Check(TEXT("MID / Nanite"),bMID);
        Group(2);
        Check(TEXT("3. Один общий кадр"),bRender);
        Check(TEXT("Каждый MID"),bRenderMID); Check(TEXT("Каждый LOW / LOD0"),bRenderLOW);
        Check(TEXT("Каждый LOD"),bRenderLODS); Check(TEXT("Один выбранный LOD каждой модели"),bRenderSelected);
        Field(TEXT("Номер выбранного LOD (0–4)"),SelectedLOD,TEXT("0"));
        Group(3);
        Check(TEXT("4. Чистый проект + проверка + ZIP"),bZip);
        Field(TEXT("Каталог вывода (пусто — Saved)"),Output,TEXT(""));
        Button(TEXT("Выбрать каталог вывода…"),[this](){return Browse(Output);});
        Form=Main;
        Button(TEXT("Проверить исходники"),[this](){return Send(TEXT("plan"));});
        Button(TEXT("Запустить подготовку"),[this](){return Send(TEXT("start"));});
        Button(TEXT("Остановить"),[this](){return Send(TEXT("cancel"));});
        TSharedPtr<SVerticalBox> Pro;
        Form->AddSlot().AutoHeight()[SNew(SBox).Visibility_Lambda([this](){return Mode==TEXT("Профессиональный")?EVisibility::Visible:EVisibility::Collapsed;})[SAssignNew(Pro,SVerticalBox)]];
        Form=Pro;
        auto ProField=[this](const TCHAR* Id,const TCHAR* Label,const TCHAR* Default){Field(Label,ProfessionalFields.FindOrAdd(Id),Default);};
        ProField(TEXT("destination_root"),TEXT("Назначение в Content"),TEXT("/Game/MyAssetPack"));
        ProField(TEXT("asset_ids"),TEXT("ID моделей через запятую (пусто — все)"),TEXT(""));
        ProField(TEXT("mesh_info"),TEXT("Файл каталога моделей"),TEXT("MeshInfo.json"));
        ProField(TEXT("texture_directory"),TEXT("Папка текстур относительно исходников"),TEXT("FBX/Textures"));
        ProField(TEXT("lod_screen_sizes"),TEXT("Screen sizes LOD"),TEXT("1, 0.5, 0.25, 0.125, 0.0625"));
        ProField(TEXT("nanite_source"),TEXT("Источник Nanite: AUTO / MID / HIGH"),TEXT("AUTO"));
        ProField(TEXT("collision"),TEXT("Коллизия: none / box"),TEXT("box"));
        ProField(TEXT("roughness"),TEXT("Материал · Roughness"),TEXT("0.85"));
        ProField(TEXT("metallic"),TEXT("Материал · Metallic"),TEXT("0"));
        ProField(TEXT("normal_strength"),TEXT("Материал · Normal strength"),TEXT("1"));
        ProField(TEXT("uv_scale"),TEXT("Материал · UV scale"),TEXT("1"));
        ProField(TEXT("orm_texture"),TEXT("Материал · ORM текстура (необязательно)"),TEXT(""));
        ProField(TEXT("overview_columns"),TEXT("Обзор · столбцов"),TEXT("4"));
        ProField(TEXT("overview_spacing"),TEXT("Обзор · расстояние, см"),TEXT("100"));
        ProField(TEXT("overview_label_size"),TEXT("Обзор · размер подписей"),TEXT("5"));
        ProField(TEXT("preview_width"),TEXT("Рендер · ширина"),TEXT("1920"));
        ProField(TEXT("preview_height"),TEXT("Рендер · высота"),TEXT("1080"));
        ProField(TEXT("preview_warmup"),TEXT("Рендер · прогрев, секунд"),TEXT("5"));
        ProField(TEXT("media_pitch"),TEXT("Предметные кадры · наклон"),TEXT("15"));
        ProField(TEXT("media_fov"),TEXT("Предметные кадры · FOV"),TEXT("40"));
        ProField(TEXT("media_margin"),TEXT("Предметные кадры · запас кадра"),TEXT("1.18"));
        ProField(TEXT("media_exposure"),TEXT("Предметные кадры · экспокоррекция"),TEXT("-0.75"));
        ProField(TEXT("flythrough_seconds"),TEXT("Пролёт · длительность, секунд"),TEXT("8"));
        ProField(TEXT("flythrough_fps"),TEXT("Пролёт · FPS"),TEXT("24"));
        ProField(TEXT("flythrough_width"),TEXT("Пролёт · ширина"),TEXT("1280"));
        ProField(TEXT("flythrough_height"),TEXT("Пролёт · высота"),TEXT("720"));
        ProField(TEXT("flythrough_yaw_start"),TEXT("Пролёт · начальный ракурс"),TEXT("65"));
        ProField(TEXT("flythrough_yaw_end"),TEXT("Пролёт · конечный ракурс"),TEXT("115"));
        ProField(TEXT("flythrough_pitch"),TEXT("Пролёт · наклон"),TEXT("25"));
        ProField(TEXT("flythrough_fov"),TEXT("Пролёт · FOV"),TEXT("50"));
        Button(TEXT("Создать и отрендерить пролёт первого выбранного профиля"),[this](){return Send(TEXT("flythrough"));});
        Check(TEXT("Служебный режим: использовать JSON вместо форм"),bRawProfile);
        Button(TEXT("Сохранить активный профиль"),[this](){return Send(TEXT("save_profile"));});
        Button(TEXT("Проверить импортированные ассеты"),[this](){return Send(TEXT("validate_assets"));});
        Button(TEXT("Применить настройки к существующим ассетам"),[this](){return Send(TEXT("settings"));});
        Form->AddSlot().AutoHeight().Padding(0,14)[SNew(STextBlock).Text(FText::FromString(TEXT("Индивидуальные настройки модели · пусто = наследовать")))];
        Field(TEXT("ID модели"),OverrideID,TEXT(""));
        auto OverrideField=[this](const TCHAR* Id,const TCHAR* Label){Field(Label,OverrideFields.FindOrAdd(Id),TEXT(""));};
        OverrideField(TEXT("lod_screen_sizes"),TEXT("Screen sizes этой модели (то же число LOD)"));
        OverrideField(TEXT("nanite_source"),TEXT("Источник Nanite: inherit / AUTO / MID / HIGH"));
        OverrideField(TEXT("collision"),TEXT("Коллизия: inherit / none / box"));
        OverrideField(TEXT("remove_degenerates"),TEXT("Remove Degenerates: inherit / true / false"));
        OverrideField(TEXT("roughness"),TEXT("Roughness"));
        OverrideField(TEXT("metallic"),TEXT("Metallic"));
        OverrideField(TEXT("normal_strength"),TEXT("Normal strength"));
        OverrideField(TEXT("uv_scale"),TEXT("UV scale"));
        OverrideField(TEXT("orm_texture"),TEXT("ORM: пусто = общий; - = отключить"));
        Button(TEXT("Загрузить индивидуальные настройки из профиля UI"),[this](){return Send(TEXT("override_load"));});
        Button(TEXT("Записать индивидуальные настройки в профиль UI"),[this](){return Send(TEXT("override_store"));});
        Button(TEXT("Удалить индивидуальные настройки из профиля UI"),[this](){return Send(TEXT("override_delete"));});
        Button(TEXT("Диагностика исходных FBX / GLB (без импорта)"),[this](){return Send(TEXT("source_diagnostics"));});
        Button(TEXT("Диагностика импорта LOW/LOD (создаёт тестовые ассеты)"),[this](){return Send(TEXT("import_diagnostics"));});
        Button(TEXT("Очередь: обновить список запусков"),[this](){return Send(TEXT("queue"));});
        Form->AddSlot().AutoHeight()[Combo(Runs,RunID,&RunMenu)];
        Button(TEXT("Показать отчёт выбранного запуска"),[this](){return Send(TEXT("job_status"));});
        Button(TEXT("Возобновить выбранный запуск"),[this](){return Send(TEXT("resume"));});
        Form=Main;
        Form->AddSlot().AutoHeight().Padding(0,12)[SNew(STextBlock).Visibility_Lambda([this](){return Mode==TEXT("Профессиональный")?EVisibility::Visible:EVisibility::Collapsed;}).Text(FText::FromString(TEXT("Служебный JSON — приоритет только при включённом флажке"))).AutoWrapText(true)];
        Form->AddSlot().AutoHeight()[SNew(SBox).Visibility_Lambda([this](){return Mode==TEXT("Профессиональный")?EVisibility::Visible:EVisibility::Collapsed;}).HeightOverride(220)[SAssignNew(Advanced,SMultiLineEditableTextBox)]];
        Button(TEXT("Загрузить активный профиль в редактор JSON"),[this](){
            return Send(TEXT("load_profile"));});
        Button(TEXT("Content: сканировать папки / очистка…"),[this](){bShowContent=true;return Send(TEXT("scan_content"));});
        TSharedPtr<SVerticalBox> ContentBody;
        Main->AddSlot().AutoHeight()[SNew(SBox).Visibility_Lambda([this](){return bShowContent?EVisibility::Visible:EVisibility::Collapsed;})[SAssignNew(ContentBody,SVerticalBox)]];
        Form=ContentBody;
        Form->AddSlot().AutoHeight()[Combo(Folders,CleanupRoot,&FolderMenu)];
        Button(TEXT("Content: показать план очистки выбранной папки"),[this](){return Send(TEXT("cleanup_plan"));});
        Button(TEXT("Content: подтвердить удаление по просмотренному плану…"),[this](){
            if(FMessageDialog::Open(EAppMsgType::YesNo,FText::FromString(TEXT("Удалить ассеты выбранной папки по ранее показанному плану? Будет сделана резервная копия. Исходники не затрагиваются.")))==EAppReturnType::Yes) return Send(TEXT("cleanup_confirm"));
            return FReply::Handled();});
        Form=Main;
        Button(TEXT("OpenAI: настройки и чат…"),[this](){bShowAI=!bShowAI;return FReply::Handled();});
        TSharedPtr<SVerticalBox> AIBody;
        Main->AddSlot().AutoHeight()[SNew(SBox).Visibility_Lambda([this](){return bShowAI?EVisibility::Visible:EVisibility::Collapsed;})[SAssignNew(AIBody,SVerticalBox)]];
        Form=AIBody;
        Form->AddSlot().AutoHeight().Padding(0,14)[SNew(STextBlock).Text(FText::FromString(TEXT("OpenAI · Настройки и помощник")))];
        Form->AddSlot().AutoHeight()[SAssignNew(Key,SEditableTextBox).IsPassword(true).HintText(FText::FromString(TEXT("Новый API-ключ (пусто — текущий)")))];
        Check(TEXT("Запомнить ключ на этом компьютере (Windows DPAPI)"),bRemember);
        Form->AddSlot().AutoHeight()[Combo(Models,Model,&ModelMenu)];
        Button(TEXT("Применить настройки OpenAI"),[this](){return Send(TEXT("ai_save"));});
        Button(TEXT("Проверить ключ / обновить модели"),[this](){return Send(TEXT("ai_models"));});
        for(const TCHAR* Name:{TEXT("Только советы"),TEXT("Подтверждать действия"),TEXT("Автоматически")}) Permissions.Add(MakeShared<FString>(Name));
        Form->AddSlot().AutoHeight().Padding(0,8)[Combo(Permissions,Permission)];
        Form->AddSlot().AutoHeight()[SNew(STextBlock).AutoWrapText(true).Text(FText::FromString(TEXT("AI может проверить исходники, запустить подготовку, прочитать статус и остановить задачу. Удаление и произвольный Python недоступны.")))];
        Form->AddSlot().AutoHeight()[SNew(SBox).HeightOverride(240)[SAssignNew(ChatHistory,SMultiLineEditableTextBox).IsReadOnly(true)]];
        Form->AddSlot().AutoHeight()[SAssignNew(Chat,SEditableTextBox).HintText(FText::FromString(TEXT("Вопрос помощнику; не вводите секреты. Текст будет передан OpenAI.")))];
        Button(TEXT("Отправить вопрос OpenAI"),[this](){return Send(TEXT("chat"));});
        Form->AddSlot().AutoHeight().Padding(0,6)[SNew(SButton).Text(FText::FromString(TEXT("Подтвердить предложенное действие…")))
            .IsEnabled_Lambda([this](){return bAIPending;}).OnClicked_Lambda([this](){
                if(FMessageDialog::Open(EAppMsgType::YesNo,FText::FromString(TEXT("Выполнить предложение AI со снимком параметров, показанным в чате?")))==EAppReturnType::Yes) return Send(TEXT("ai_approve"));
                return FReply::Handled();})];
        Button(TEXT("Отклонить предложение AI"),[this](){return Send(TEXT("ai_reject"));});
        Button(TEXT("Очистить историю чата"),[this](){return Send(TEXT("chat_clear"));});
        Form=Main;
        Button(TEXT("Показать / скрыть журнал задач"),[this](){bShowJournal=!bShowJournal;return FReply::Handled();});
        Form->AddSlot().AutoHeight()[SNew(SBox).Visibility_Lambda([this](){return bShowJournal?EVisibility::Visible:EVisibility::Collapsed;}).HeightOverride(240)[SAssignNew(TaskHistory,SMultiLineEditableTextBox).IsReadOnly(true)]];
        Button(TEXT("Открыть папку отчётов"),[](){FPlatformProcess::ExploreFolder(*(FPaths::ProjectSavedDir()/TEXT("AssetPackPipeline")));return FReply::Handled();});
        Form->AddSlot().AutoHeight().Padding(0,12)[SAssignNew(Status,STextBlock).AutoWrapText(true)];
        RegisterActiveTimer(0.5f,FWidgetActiveTimerDelegate::CreateLambda([this](double,float){Refresh();return EActiveTimerReturnType::Continue;}));
    }
};

class FAssetPackPipelineEditorModule : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        if (!IsRunningCommandlet()) FGlobalTabmanager::Get()->RegisterNomadTabSpawner(PipelineTab,
            FOnSpawnTab::CreateLambda([](const FSpawnTabArgs&){TSharedRef<SPipelinePanel> Panel=SNew(SPipelinePanel); LivePipelinePanel=Panel; return SNew(SDockTab).TabRole(ETabRole::NomadTab)[Panel];}))
            .SetDisplayName(FText::FromString(TEXT("Asset Pack Pipeline"))).SetMenuType(ETabSpawnerMenuType::Hidden);
    }
    virtual void ShutdownModule() override
    {
        if (!IsRunningCommandlet()) FGlobalTabmanager::Get()->UnregisterNomadTabSpawner(PipelineTab);
    }
};
IMPLEMENT_MODULE(FAssetPackPipelineEditorModule, AssetPackPipelineEditor)
void UAssetPackPipelineNative::OpenWindow(){ LivePipelineTab=FGlobalTabmanager::Get()->TryInvokeTab(PipelineTab); }
bool UAssetPackPipelineNative::IsWindowOpen(){ return LivePipelineTab.IsValid(); }
void UAssetPackPipelineNative::CloseWindow(){ if(auto Tab=LivePipelineTab.Pin()) Tab->RequestCloseTab(); LivePipelineTab.Reset(); }
bool UAssetPackPipelineNative::RunUIRegressionStep(int32 Iteration){if(auto Panel=LivePipelinePanel.Pin()) return Panel->Exercise(FMath::Max(0,Iteration)); return false;}
