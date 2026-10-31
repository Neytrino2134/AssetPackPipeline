#include "AssetPackPipelineNative.h"
#include "Modules/ModuleManager.h"
#include "Framework/Docking/TabManager.h"
#include "Widgets/Docking/SDockTab.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/SBoxPanel.h"
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
    bool IsPro() const {return Mode==TEXT("Профессиональный");}
    bool IsWizard() const {return Mode==TEXT("Мастер");}
    bool IsQuick() const {return !IsPro() && !IsWizard();}
    static EVisibility Visible(bool bShown){return bShown ? EVisibility::Visible : EVisibility::Collapsed;}
    const TCHAR* StageTitles[4]={TEXT("Источники и импорт"),TEXT("Меши, LOD и Nanite"),TEXT("Рендер и предметные кадры"),TEXT("Поставка")};
    TSharedPtr<SVerticalBox> MainBox;
    TArray<bool> SectionOpen;
    TArray<TSharedPtr<SVerticalBox>> OnlyStack;
    /** Starts a stage group on the main column and redirects Form into its body.
     *  WizardStep>=0: shared stage (Quick: always, Master: on its step, Professional: collapsible).
     *  WizardStep<0: Professional-only collapsible group unless Shown overrides it. */
    void Section(const TCHAR* Title, int32 WizardStep, bool bOpen, TFunction<bool()> Shown=nullptr)
    {
        const int32 Index=SectionOpen.Add(bOpen);
        const FString Name(Title);
        TSharedPtr<SVerticalBox> Body;
        MainBox->AddSlot().AutoHeight().Padding(0,4)[SNew(SBox).Visibility_Lambda([this,WizardStep,Shown](){
                return Visible(Shown ? Shown() : WizardStep<0 ? IsPro() : IsPro() || IsQuick() || Step==WizardStep);})
            [SNew(SVerticalBox)
            +SVerticalBox::Slot().AutoHeight()[SNew(SButton).ButtonStyle(FAppStyle::Get(),"SimpleButton")
                .Visibility_Lambda([this](){return Visible(IsPro());})
                .OnClicked_Lambda([this,Index](){SectionOpen[Index]=!SectionOpen[Index];return FReply::Handled();})
                [SNew(STextBlock).Font(FAppStyle::GetFontStyle("BoldFont")).Text_Lambda([this,Index,Name](){
                    return FText::FromString((SectionOpen[Index] ? TEXT("▼  ") : TEXT("▶  "))+Name);})]]
            +SVerticalBox::Slot().AutoHeight().Padding(0,8,0,2)[SNew(STextBlock).Font(FAppStyle::GetFontStyle("BoldFont"))
                .Visibility_Lambda([this](){return Visible(!IsPro());}).Text(FText::FromString(Name))]
            +SVerticalBox::Slot().AutoHeight()[SNew(SBorder).BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder")).Padding(FMargin(12,6))
                .Visibility_Lambda([this,Index](){return Visible(!IsPro() || SectionOpen[Index]);})
                [SAssignNew(Body,SVerticalBox)]]]];
        Form=Body;
    }
    /** Nested block inside the current group that is shown only while Predicate holds. */
    void Only(TFunction<bool()> Predicate)
    {
        TSharedPtr<SVerticalBox> Body;
        Form->AddSlot().AutoHeight()[SNew(SBox).Visibility_Lambda([Predicate](){return Visible(Predicate());})[SAssignNew(Body,SVerticalBox)]];
        OnlyStack.Push(Form); Form=Body;
    }
    void EndOnly(){Form=OnlyStack.Pop();}
    void ProField(const TCHAR* Id, const TCHAR* Label, const TCHAR* Default){Field(Label,ProfessionalFields.FindOrAdd(Id),Default);}
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
        TSharedPtr<SVerticalBox> Main=Form;
        MainBox=Main;
        Form->AddSlot().AutoHeight().Padding(0,10)[SNew(STextBlock).Text(FText::FromString(TEXT("MESHFLOW Asset Pack Pipeline"))).Font(FAppStyle::GetFontStyle("HeadingExtraSmall"))];
        for(const TCHAR* Name:{TEXT("Быстрый старт"),TEXT("Мастер"),TEXT("Профессиональный")}) Modes.Add(MakeShared<FString>(Name));
        for(const TCHAR* Name:{TEXT("FBX"),TEXT("GLB")}) Formats.Add(MakeShared<FString>(Name));
        for(const TCHAR* Name:{TEXT("gpt-6.1-sol"),TEXT("gpt-6-astra"),TEXT("gpt-6.1-terra"),TEXT("gpt-6-luna")}) Models.Add(MakeShared<FString>(Name));
        Form->AddSlot().AutoHeight().Padding(0,8)[Combo(Modes,Mode)];
        Form->AddSlot().AutoHeight().Padding(0,0,0,8)[SNew(STextBlock).AutoWrapText(true).ColorAndOpacity(FSlateColor::UseSubduedForeground()).Text_Lambda([this](){
            if(IsPro()) return FText::FromString(TEXT("Профессиональный: все параметры по этапам и служебные инструменты. Разверните нужную группу."));
            if(IsWizard()) return FText::FromString(FString::Printf(TEXT("Мастер · шаг %d из 4 — %s. Помощник OpenAI доступен ниже."),Step+1,StageTitles[Step]));
            return FText::FromString(TEXT("Быстрый старт: исходники → меши → общий кадр → проверенный ZIP."));})];

        // Shared stages: Quick shows all, Master shows one step at a time,
        // Professional wraps each in a collapsible group with extra fields.
        Section(TEXT("Источники и импорт"),0,true);
        Field(TEXT("Папка исходников"),Source,TEXT(""));
        Button(TEXT("Выбрать исходники…"),[this](){return Browse(Source);});
        Field(TEXT("Имя пака (латиница)"),Pack,TEXT("MyAssetPack"));
        Form->AddSlot().AutoHeight().Padding(0,8)[Combo(Formats,FormatValue)];
        Only([this](){return IsPro();});
        ProField(TEXT("destination_root"),TEXT("Назначение в Content"),TEXT("/Game/MyAssetPack"));
        ProField(TEXT("asset_ids"),TEXT("ID моделей через запятую (пусто — все)"),TEXT(""));
        ProField(TEXT("mesh_info"),TEXT("Файл каталога моделей"),TEXT("MeshInfo.json"));
        ProField(TEXT("texture_directory"),TEXT("Папка текстур относительно исходников"),TEXT("FBX/Textures"));
        EndOnly();
        Only([this](){return !IsWizard() || Step==0;});
        Button(TEXT("Проверить исходники"),[this](){return Send(TEXT("plan"));});
        EndOnly();

        Section(TEXT("Меши, LOD и Nanite"),1,true);
        Check(TEXT("LOW / LOD"),bLOD); Check(TEXT("MID / Nanite"),bMID);
        Only([this](){return IsPro();});
        ProField(TEXT("lod_screen_sizes"),TEXT("Screen sizes LOD"),TEXT("1, 0.5, 0.25, 0.125, 0.0625"));
        ProField(TEXT("nanite_source"),TEXT("Источник Nanite: AUTO / MID / HIGH"),TEXT("AUTO"));
        ProField(TEXT("collision"),TEXT("Коллизия: none / box"),TEXT("box"));
        EndOnly();

        Section(TEXT("Материалы"),-1,false);
        ProField(TEXT("roughness"),TEXT("Roughness"),TEXT("0.85"));
        ProField(TEXT("metallic"),TEXT("Metallic"),TEXT("0"));
        ProField(TEXT("normal_strength"),TEXT("Normal strength"),TEXT("1"));
        ProField(TEXT("uv_scale"),TEXT("UV scale"),TEXT("1"));
        ProField(TEXT("orm_texture"),TEXT("ORM текстура (необязательно)"),TEXT(""));

        Section(TEXT("Обзорная сцена"),-1,false);
        ProField(TEXT("overview_columns"),TEXT("Столбцов"),TEXT("4"));
        ProField(TEXT("overview_spacing"),TEXT("Расстояние, см"),TEXT("100"));
        ProField(TEXT("overview_label_size"),TEXT("Размер подписей"),TEXT("5"));

        Section(TEXT("Рендер и предметные кадры"),2,false);
        Check(TEXT("Один общий кадр"),bRender);
        Only([this](){return !IsQuick();});
        Check(TEXT("Каждый MID"),bRenderMID); Check(TEXT("Каждый LOW / LOD0"),bRenderLOW);
        Check(TEXT("Каждый LOD"),bRenderLODS); Check(TEXT("Один выбранный LOD каждой модели"),bRenderSelected);
        Field(TEXT("Номер выбранного LOD (0–4)"),SelectedLOD,TEXT("0"));
        EndOnly();
        Only([this](){return IsPro();});
        ProField(TEXT("preview_width"),TEXT("Рендер · ширина"),TEXT("1920"));
        ProField(TEXT("preview_height"),TEXT("Рендер · высота"),TEXT("1080"));
        ProField(TEXT("preview_warmup"),TEXT("Рендер · прогрев, секунд"),TEXT("5"));
        ProField(TEXT("media_pitch"),TEXT("Предметные кадры · наклон"),TEXT("15"));
        ProField(TEXT("media_fov"),TEXT("Предметные кадры · FOV"),TEXT("40"));
        ProField(TEXT("media_margin"),TEXT("Предметные кадры · запас кадра"),TEXT("1.18"));
        ProField(TEXT("media_exposure"),TEXT("Предметные кадры · экспокоррекция"),TEXT("-0.75"));
        EndOnly();

        Section(TEXT("Пролёт камеры"),-1,false);
        ProField(TEXT("flythrough_seconds"),TEXT("Длительность, секунд"),TEXT("8"));
        ProField(TEXT("flythrough_fps"),TEXT("FPS"),TEXT("24"));
        ProField(TEXT("flythrough_width"),TEXT("Ширина"),TEXT("1280"));
        ProField(TEXT("flythrough_height"),TEXT("Высота"),TEXT("720"));
        ProField(TEXT("flythrough_yaw_start"),TEXT("Начальный ракурс"),TEXT("65"));
        ProField(TEXT("flythrough_yaw_end"),TEXT("Конечный ракурс"),TEXT("115"));
        ProField(TEXT("flythrough_pitch"),TEXT("Наклон"),TEXT("25"));
        ProField(TEXT("flythrough_fov"),TEXT("FOV"),TEXT("50"));
        Button(TEXT("Создать и отрендерить пролёт первого выбранного профиля"),[this](){return Send(TEXT("flythrough"));});

        Section(TEXT("Поставка"),3,false);
        Check(TEXT("Чистый проект + проверка + ZIP"),bZip);
        Field(TEXT("Каталог вывода (пусто — Saved)"),Output,TEXT(""));
        Button(TEXT("Выбрать каталог вывода…"),[this](){return Browse(Output);});
        Form=Main;

        // Master navigation lives only in Master mode.
        Form->AddSlot().AutoHeight().Padding(0,10)[SNew(SHorizontalBox).Visibility_Lambda([this](){return Visible(IsWizard());})
            +SHorizontalBox::Slot().AutoWidth().Padding(0,0,8,0)[SNew(SButton).Text(FText::FromString(TEXT("← Назад")))
                .IsEnabled_Lambda([this](){return Step>0;}).OnClicked_Lambda([this](){Step=FMath::Max(0,Step-1);return FReply::Handled();})]
            +SHorizontalBox::Slot().AutoWidth()[SNew(SButton).Text(FText::FromString(TEXT("Далее →")))
                .Visibility_Lambda([this](){return Visible(Step<3);}).OnClicked_Lambda([this](){Step=FMath::Min(3,Step+1);return FReply::Handled();})]];
        Form->AddSlot().AutoHeight().Padding(0,6)[SNew(SHorizontalBox)
            +SHorizontalBox::Slot().AutoWidth().Padding(0,0,8,0)[SNew(SButton).Text(FText::FromString(TEXT("Запустить подготовку")))
                .Visibility_Lambda([this](){return Visible(!IsWizard() || Step==3);}).OnClicked_Lambda([this](){return Send(TEXT("start"));})]
            +SHorizontalBox::Slot().AutoWidth()[SNew(SButton).Text(FText::FromString(TEXT("Остановить"))).OnClicked_Lambda([this](){return Send(TEXT("cancel"));})]];

        // Professional-only service groups.
        Section(TEXT("Индивидуальные настройки моделей"),-1,false);
        Form->AddSlot().AutoHeight()[SNew(STextBlock).Text(FText::FromString(TEXT("Пусто = наследовать общий профиль")))];
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
        Button(TEXT("Загрузить из профиля UI"),[this](){return Send(TEXT("override_load"));});
        Button(TEXT("Записать в профиль UI"),[this](){return Send(TEXT("override_store"));});
        Button(TEXT("Удалить из профиля UI"),[this](){return Send(TEXT("override_delete"));});

        Section(TEXT("Проверка и диагностика"),-1,false);
        Button(TEXT("Проверить импортированные ассеты"),[this](){return Send(TEXT("validate_assets"));});
        Button(TEXT("Применить настройки к существующим ассетам"),[this](){return Send(TEXT("settings"));});
        Button(TEXT("Диагностика исходных FBX / GLB (без импорта)"),[this](){return Send(TEXT("source_diagnostics"));});
        Button(TEXT("Диагностика импорта LOW/LOD (создаёт тестовые ассеты)"),[this](){return Send(TEXT("import_diagnostics"));});

        Section(TEXT("Очередь запусков"),-1,false);
        Button(TEXT("Обновить список запусков"),[this](){return Send(TEXT("queue"));});
        Form->AddSlot().AutoHeight()[Combo(Runs,RunID,&RunMenu)];
        Button(TEXT("Показать отчёт выбранного запуска"),[this](){return Send(TEXT("job_status"));});
        Button(TEXT("Возобновить выбранный запуск"),[this](){return Send(TEXT("resume"));});

        Section(TEXT("Профиль и служебный JSON"),-1,false);
        Button(TEXT("Сохранить активный профиль"),[this](){return Send(TEXT("save_profile"));});
        Button(TEXT("Загрузить активный профиль в редактор JSON"),[this](){return Send(TEXT("load_profile"));});
        Check(TEXT("Служебный режим: использовать JSON вместо форм"),bRawProfile);
        Form->AddSlot().AutoHeight().Padding(0,6)[SNew(STextBlock).Text(FText::FromString(TEXT("Служебный JSON — приоритет только при включённом флажке"))).AutoWrapText(true)];
        Form->AddSlot().AutoHeight()[SNew(SBox).HeightOverride(220)[SAssignNew(Advanced,SMultiLineEditableTextBox)]];

        Section(TEXT("Content: сканирование и очистка"),-1,false);
        Button(TEXT("Сканировать папки Content"),[this](){bShowContent=true;return Send(TEXT("scan_content"));});
        TSharedPtr<SVerticalBox> ContentBody;
        Form->AddSlot().AutoHeight()[SNew(SBox).Visibility_Lambda([this](){return Visible(bShowContent);})[SAssignNew(ContentBody,SVerticalBox)]];
        Form=ContentBody;
        Form->AddSlot().AutoHeight()[Combo(Folders,CleanupRoot,&FolderMenu)];
        Button(TEXT("Показать план очистки выбранной папки"),[this](){return Send(TEXT("cleanup_plan"));});
        Button(TEXT("Подтвердить удаление по просмотренному плану…"),[this](){
            if(FMessageDialog::Open(EAppMsgType::YesNo,FText::FromString(TEXT("Удалить ассеты выбранной папки по ранее показанному плану? Будет сделана резервная копия. Исходники не затрагиваются.")))==EAppReturnType::Yes) return Send(TEXT("cleanup_confirm"));
            return FReply::Handled();});

        // OpenAI: a toggle in Master, a collapsible group in Professional, hidden in Quick start.
        Form=Main;
        Form->AddSlot().AutoHeight().Padding(0,6)[SNew(SButton).Text(FText::FromString(TEXT("Помощник OpenAI: показать / скрыть")))
            .Visibility_Lambda([this](){return Visible(IsWizard());}).OnClicked_Lambda([this](){bShowAI=!bShowAI;return FReply::Handled();})];
        Section(TEXT("OpenAI · настройки и помощник"),-1,false,[this](){return IsWizard() ? bShowAI : IsPro();});
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
            .SetDisplayName(FText::FromString(TEXT("MESHFLOW Asset Pack Pipeline"))).SetMenuType(ETabSpawnerMenuType::Hidden);
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
