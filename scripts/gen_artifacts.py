"""
gen_artifacts.py
Reads /tmp/changed_files.txt and generates:
  manifest/<FEATURE_BRANCH>_package.xml
  manifest/<FEATURE_BRANCH>_TestClass.txt  (ApexClass members only)

Required env vars:
  BUILD_SOURCES   - $(Build.SourcesDirectory)
  FEATURE_BRANCH  - e.g. feature/dev_01_01_2025
  API_VERSION     - e.g. 67.0
"""
import os, sys, re
from xml.etree import ElementTree as ET

build_sources = os.environ["BUILD_SOURCES"]
branch        = os.environ["FEATURE_BRANCH"]
api_version   = os.environ.get("API_VERSION", "67.0")

with open("/tmp/changed_files.txt") as f:
    changed_files = [l.strip() for l in f if l.strip() and not l.startswith("#")]

TYPE_MAP = {
    # ── Apex & UI Components ──────────────────────────────────────────────────
    "classes":                            "ApexClass",
    "triggers":                           "ApexTrigger",
    "pages":                              "ApexPage",
    "components":                         "ApexComponent",
    "lwc":                                "LightningComponentBundle",
    "aura":                               "AuraDefinitionBundle",
    "flexipages":                         "FlexiPage",
    "staticresources":                    "StaticResource",
    "contentassets":                      "ContentAsset",
    # ── Objects & Fields ─────────────────────────────────────────────────────
    "objects":                            "CustomObject",
    "layouts":                            "Layout",
    "quickActions":                       "QuickAction",
    "globalValueSets":                    "GlobalValueSet",
    "standardValueSets":                  "StandardValueSet",
    "duplicateRules":                     "DuplicateRule",
    "matchingRules":                      "MatchingRule",
    "sharingRules":                       "SharingRules",
    "assignmentRules":                    "AssignmentRules",
    "autoResponseRules":                  "AutoResponseRules",
    "escalationRules":                    "EscalationRules",
    "approvalProcesses":                  "ApprovalProcess",
    "pathAssistants":                     "PathAssistant",
    "compactLayouts":                     "CompactLayout",
    "fieldSets":                          "FieldSet",
    "listViews":                          "ListView",
    "recordTypes":                        "RecordType",
    "validationRules":                    "ValidationRule",
    "webLinks":                           "WebLink",
    "businessProcesses":                  "BusinessProcess",
    "indexes":                            "Index",
    "sharingReasons":                     "SharingReason",
    # ── Automation ───────────────────────────────────────────────────────────
    "flows":                              "Flow",
    "flowCategories":                     "FlowCategory",
    "flowDefinitions":                    "FlowDefinition",
    "workflows":                          "Workflow",
    "processMetadataValues":              "ProcessMetadataValue",
    # ── Permissions & Security ───────────────────────────────────────────────
    "permissionsets":                     "PermissionSet",
    "permissionsetgroups":                "PermissionSetGroup",
    "permissionSetLicenseDefinitions":    "PermissionSetLicenseDefinition",
    "profiles":                           "Profile",
    "userAccessPolicies":                 "UserAccessPolicy",
    "useraccesspolicies":                 "UserAccessPolicy",
    "cspTrustedSites":                    "CspTrustedSite",
    "remoteSiteSettings":                 "RemoteSiteSetting",
    "corsWhitelistOrigins":               "CorsWhitelistOrigin",
    "connectedApps":                      "ConnectedApp",
    "authproviders":                      "AuthProvider",
    "namedCredentials":                   "NamedCredential",
    "externalCredentials":                "ExternalCredential",
    "certificates":                       "Certificate",
    "mutingPermissionSets":               "MutingPermissionSet",
    "restrictionRules":                   "RestrictionRule",
    "sharingCriteriaRules":               "SharingCriteriaRule",
    "sharingOwnerRules":                  "SharingOwnerRule",
    "sharingGuestRules":                  "SharingGuestRule",
    "sharingTerritoryRules":              "SharingTerritoryRule",
    # ── Org Configuration ────────────────────────────────────────────────────
    "settings":                           "Settings",
    "tabs":                               "CustomTab",
    "applications":                       "CustomApplication",
    "customMetadata":                     "CustomMetadata",
    "actionLinkGroupTemplates":           "ActionLinkGroupTemplate",
    "homePageComponents":                 "HomePageComponent",
    "homePageLayouts":                    "HomePageLayout",
    "customPermissions":                  "CustomPermission",
    "featureParameters":                  "FeatureParameter",
    "featureParameterBoolean":            "FeatureParameterBoolean",
    "featureParameterDate":               "FeatureParameterDate",
    "featureParameterInteger":            "FeatureParameterInteger",
    "territory2Settings":                 "Territory2Settings",
    "myDomainDiscoverableLogin":          "MyDomainDiscoverableLogin",
    "oauthCustomScopes":                  "OauthCustomScope",
    "oauthCustomScopeAccesses":           "OauthCustomScopeAccess",
    "userProvisioningConfigs":            "UserProvisioningConfig",
    "userCriteria":                       "UserCriteria",
    "cleanDataServices":                  "CleanDataService",
    "dataCategoryGroups":                 "DataCategoryGroup",
    "dataWeaveResources":                 "DataWeaveResource",
    "apexEmailNotifications":             "ApexEmailNotification",
    "postTemplates":                      "PostTemplate",
    "animationRules":                     "AnimationRule",
    "aiApplications":                     "AIApplication",
    "aiApplicationConfigs":               "AIApplicationConfig",
    "aiScoringModelDefinitions":          "AIScoringModelDefinition",
    "mlPredictionDefinitions":            "MLPredictionDefinition",
    "mlDataDefinitions":                  "MLDataDefinition",
    # ── Labels & Translations ────────────────────────────────────────────────
    "labels":                             "CustomLabels",
    "translations":                       "Translations",
    "globalValueSetTranslations":         "GlobalValueSetTranslation",
    "standardValueSetTranslations":       "StandardValueSetTranslation",
    "objectTranslations":                 "CustomObjectTranslation",
    # ── Org Structure ────────────────────────────────────────────────────────
    "queues":                             "Queue",
    "groups":                             "Group",
    "roles":                              "Role",
    "businessHours":                      "BusinessHours",
    "holidays":                           "Holiday",
    "territories":                        "Territory",
    # ── Integration & APIs ───────────────────────────────────────────────────
    "dataSources":                        "ExternalDataSource",
    "externalServiceRegistrations":       "ExternalServiceRegistration",
    "platformEventChannels":              "PlatformEventChannel",
    "platformEventChannelMembers":        "PlatformEventChannelMember",
    "messageChannels":                    "LightningMessageChannel",
    "eventDeliveries":                    "EventDelivery",
    "eventSubscriptions":                 "EventSubscription",
    "integrationHubs":                    "IntegrationHub",
    "apexTestSuites":                     "ApexTestSuite",
    # ── Analytics & Reports ──────────────────────────────────────────────────
    "reportTypes":                        "ReportType",
    "analyticSnapshots":                  "AnalyticSnapshot",
    "reports":                            "Report",
    "dashboards":                         "Dashboard",
    "analyticsDataflows":                 "DataflowJob",
    "waveApplications":                   "WaveApplication",
    "waveDashboards":                     "WaveDashboard",
    "waveDataflows":                      "WaveDataflow",
    "waveDatasets":                       "WaveDataset",
    "waveLenses":                         "WaveLens",
    "waveRecipes":                        "WaveRecipe",
    "waveTemplates":                      "WaveTemplateBundle",
    "waveXmds":                           "WaveXmd",
    # ── Communities / Experience Cloud ───────────────────────────────────────
    "experiences":                        "ExperienceBundle",
    "networks":                           "Network",
    "networkBranding":                    "NetworkBranding",
    "managedTopics":                      "ManagedTopic",
    "sites":                              "CustomSite",
    "communities":                        "Community",
    "customHelpMenuSections":             "CustomHelpMenuSection",
    "navigationMenus":                    "NavigationMenu",
    "digitalExperienceConfigs":           "DigitalExperienceConfig",
    "digitalExperienceBundles":           "DigitalExperienceBundle",
    # ── Notifications ────────────────────────────────────────────────────────
    "notificationtypes":                  "CustomNotificationType",
    "notificationTypeConfig":             "CustomNotificationType",
    "inAppNotificationTemplates":         "InAppNotificationTemplate",
    # ── Email & Templates ────────────────────────────────────────────────────
    "emailTemplates":                     "EmailTemplate",
    "documents":                          "Document",
    "letterheads":                        "Letterhead",
    "emailServicesAddresses":             "EmailServicesAddress",
    "emailServicesConfigs":               "EmailServicesConfig",
    # ── Service Cloud ────────────────────────────────────────────────────────
    "callCenters":                        "CallCenter",
    "serviceChannels":                    "ServiceChannel",
    "servicePresenceStatuses":            "ServicePresenceStatus",
    "presenceDeclineReasons":             "PresenceDeclineReason",
    "presenceUserConfigs":                "PresenceUserConfig",
    "routingConfigurations":              "RoutingConfiguration",
    "queueRoutingConfigs":                "QueueRoutingConfig",
    "skills":                             "Skill",
    "milestoneTypes":                     "MilestoneType",
    "entitlementProcesses":               "EntitlementProcess",
    "entitlementTemplates":               "EntitlementTemplate",
    "slaProcesses":                       "SlaProcess",
    "caseSubjectParticles":               "CaseSubjectParticle",
    "supportFeatureSettings":             "SupportFeatureSetting",
    "macros":                             "Macro",
    "macroInstructions":                  "MacroInstruction",
    # ── Field Service ────────────────────────────────────────────────────────
    "appointmentSchedulingPolicies":      "AppointmentSchedulingPolicy",
    "workTypes":                          "WorkType",
    "workTypeGroups":                     "WorkTypeGroup",
    "operatingHours":                     "OperatingHours",
    "serviceAppointmentSettings":         "ServiceAppointmentSettings",
    "serviceTerritory":                   "ServiceTerritory",
    "serviceTerritoryMember":             "ServiceTerritoryMember",
    # ── Bots & Einstein ──────────────────────────────────────────────────────
    "bots":                               "Bot",
    "botVersions":                        "BotVersion",
    "einsteingptPromptTemplates":         "GenAiPromptTemplate",
    "genAiPlugins":                       "GenAiPlugin",
    "genAiFunctions":                     "GenAiFunction",
    "genAiPlanners":                      "GenAiPlanner",
    # ── Territory 2.0 ────────────────────────────────────────────────────────
    "territory2Models":                   "Territory2Model",
    # ── Salesforce CPQ / Industries ──────────────────────────────────────────
    "decisionMatrices":                   "DecisionMatrix",
    "decisionMatrixDefinitions":          "DecisionMatrixDefinition",
    "expressionSetDefinitions":           "ExpressionSetDefinition",
    "expressionSets":                     "ExpressionSet",
    "omniDataTransforms":                 "OmniDataTransform",
    "omniIntegrationProcedures":          "OmniIntegrationProcedure",
    "omniScripts":                        "OmniScript",
    "omniUiCards":                        "OmniUiCard",
    "documentGenerationSettings":         "DocumentGenerationSetting",
    # ── Slack / Enablement ───────────────────────────────────────────────────
    "slackApps":                          "SlackApp",
    "enablementPrograms":                 "EnablementProgram",
    "enablementMeasureDefinitions":       "EnablementMeasureDefinition",
    # ── Misc Deployable Types ────────────────────────────────────────────────
    "audience":                           "Audience",
    "audiences":                          "Audience",
    "brandingSets":                       "BrandingSet",
    "cmsConnectSources":                  "CMSConnectSource",
    "contentBuilderElements":             "ContentBuilderElement",
    "conversationMessageDefinitions":     "ConversationMessageDefinition",
    "conversationVendorInfos":            "ConversationVendorInfo",
    "customFeedFilters":                  "CustomFeedFilter",
    "customIndex":                        "CustomIndex",
    "customObjectTranslations":           "CustomObjectTranslation",
    "dashboardFolders":                   "DashboardFolder",
    "documentFolders":                    "DocumentFolder",
    "emailTemplateFolders":               "EmailTemplateFolder",
    "embeddedServiceBranding":            "EmbeddedServiceBranding",
    "embeddedServiceConfig":              "EmbeddedServiceConfig",
    "embeddedServiceFlowConfig":          "EmbeddedServiceFlowConfig",
    "embeddedServiceLiveAgent":           "EmbeddedServiceLiveAgent",
    "embeddedServiceMenuSettings":        "EmbeddedServiceMenuSettings",
    "experiencePropertyTypeBundles":      "ExperiencePropertyTypeBundle",
    "externalApplications":               "ExternalApplication",
    "externalDataConnectors":             "ExternalDataConnector",
    "flowTests":                          "FlowTest",
    "identityVerificationProcDefs":       "IdentityVerificationProcDef",
    "inboundNetworkConnections":          "InboundNetworkConnection",
    "inboundNetworkPolicies":             "InboundNetworkPolicy",
    "installedPackages":                  "InstalledPackage",
    "ipAddressRanges":                    "IpAddressRange",
    "keywordLists":                       "KeywordList",
    "liveChatAgentConfigs":               "LiveChatAgentConfig",
    "liveChatButtons":                    "LiveChatButton",
    "liveChatDeployments":                "LiveChatDeployment",
    "liveChatSensitiveDataRules":         "LiveChatSensitiveDataRule",
    "managedContentTypes":                "ManagedContentType",
    "marketingAppExtensions":             "MarketingAppExtension",
    "mobileApplicationDetails":           "MobileApplicationDetail",
    "moderationRules":                    "ModerationRule",
    "outboundNetworkConnections":         "OutboundNetworkConnection",
    "packageVersions":                    "PackageVersion",
    "paymentGatewayProviders":            "PaymentGatewayProvider",
    "recommendationStrategies":           "RecommendationStrategy",
    "redirectWhitelistUrls":              "RedirectWhitelistUrl",
    "reportFolders":                      "ReportFolder",
    "samlSsoConfigs":                     "SamlSsoConfig",
    "searchLayouts":                      "SearchLayouts",
    "serviceAISetupDefinitions":          "ServiceAISetupDefinition",
    "serviceAISetupFields":               "ServiceAISetupField",
    "siteSettings":                       "SiteSettings",
    "socialCustomerServiceSettings":      "SocialCustomerServiceSettings",
    "synonymDictionaries":                "SynonymDictionary",
    "topicsForObjects":                   "TopicsForObjects",
    "transactionSecurityPolicies":        "TransactionSecurityPolicy",
    "uiObjectRelationConfigs":            "UiObjectRelationConfig",
    "userEngagementSettings":             "UserEngagementSettings",
    "userInterfaceSettings":              "UserInterfaceSettings",
    "waveAnalyticAssetCollections":       "WaveAnalyticAssetCollection",
    "waveDataConnectors":                 "WaveDataConnector",
    "webStoreTemplates":                  "WebStoreTemplate",
    "webStores":                          "WebStore",
    "workDotComSettings":                 "WorkDotComSettings",
    "workflowAlerts":                     "WorkflowAlert",
    "workflowFieldUpdates":               "WorkflowFieldUpdate",
    "workflowFlowActions":                "WorkflowFlowAction",
    "workflowKnowledgePublishes":         "WorkflowKnowledgePublish",
    "workflowOutboundMessages":           "WorkflowOutboundMessage",
    "workflowRules":                      "WorkflowRule",
    "workflowSends":                      "WorkflowSend",
    "workflowTasks":                      "WorkflowTask",
}
SUB_TYPE_MAP = {
    "fields":            "CustomField",
    "validationRules":   "ValidationRule",
    "recordTypes":       "RecordType",
    "listViews":         "ListView",
    "webLinks":          "WebLink",
    "compactLayouts":    "CompactLayout",
    "fieldSets":         "FieldSet",
    "businessProcesses": "BusinessProcess",
    "indexes":           "Index",
    "sharingReasons":    "SharingReason",
}
BUNDLE_TYPES = {"lwc", "aura", "experiences", "networks", "communities"}

def strip_suffix(name):
    return re.sub(
        r'\.(field|fields|validationRule|recordType|listView|webLink|compactLayout'
        r'|fieldSet|businessProcess|sharingReason|index'
        r'|layout|flexipage|flow|flowDefinition|flowCategory'
        r'|permissionset|permissionsetgroup|permissionSetLicenseDefinition|profile'
        r'|userAccessPolicy|useraccesspolicy|mutingPermissionSet|restrictionRule'
        r'|approvalProcess|assignmentRules|autoResponseRules|escalationRules'
        r'|matchingRule|sharingRules|sharingCriteriaRule|sharingOwnerRule'
        r'|sharingGuestRule|sharingTerritoryRule|duplicateRule|pathAssistant|quickAction'
        r'|workflow|workflowAlert|workflowFieldUpdate|workflowFlowAction'
        r'|workflowKnowledgePublish|workflowOutboundMessage|workflowRule|workflowSend|workflowTask'
        r'|object|tab|customMetadata|namedCredential|connectedApp'
        r'|authprovider|remoteSiteSetting|cspTrustedSite|corsWhitelistOrigin'
        r'|externalCredential|certificate|globalValueSet|standardValueSet'
        r'|globalValueSetTranslation|standardValueSetTranslation|translation|objectTranslation'
        r'|reportType|report|dashboard|emailTemplate|document|letterhead'
        r'|lightningMessageChannel|experienceBundle|network|networkBranding'
        r'|managedTopic|customSite|community|notiftype|notificationTypeConfig|customNotificationType'
        r'|callCenter|serviceChannel|servicePresenceStatus|presenceDeclineReason'
        r'|presenceUserConfig|routingConfiguration|queueRoutingConfig'
        r'|skill|milestoneType|entitlementProcess|entitlementTemplate|slaProcess'
        r'|appointmentSchedulingPolicy|workType|workTypeGroup|operatingHours'
        r'|bot|botVersion|territory2Model|territory2Type|territory2|territory2Rule'
        r'|externalDataSource|externalServiceRegistration|platformEventChannel'
        r'|platformEventChannelMember|analyticSnapshot|queue|group|role'
        r'|homePageComponent|homePageLayout|actionLinkGroupTemplate'
        r'|customPermission|featureParameter|samlSsoConfig|transactionSecurityPolicy'
        r'|embeddedServiceConfig|embeddedServiceBranding|embeddedServiceFlowConfig'
        r'|embeddedServiceLiveAgent|embeddedServiceMenuSettings'
        r'|liveChatAgentConfig|liveChatButton|liveChatDeployment|liveChatSensitiveDataRule'
        r'|navigationMenu|audience|brandingSet|keywordList|moderationRule|synonymDictionary'
        r'|topicsForObjects|recommendationStrategy|dataCategoryGroup|dataWeaveResource'
        r'|omniDataTransform|omniIntegrationProcedure|omniScript|omniUiCard'
        r'|decisionMatrix|decisionMatrixDefinition|expressionSetDefinition|expressionSet'
        r'|genAiPromptTemplate|genAiPlugin|genAiFunction|genAiPlanner'
        r'|waveApplication|waveDashboard|waveDataflow|waveDataset|waveLens|waveRecipe|waveXmd'
        r'|webStore|webStoreTemplate|slackApp|enablementProgram'
        r'|settings|site|md|resource|asset|cls|trigger|page|component'
        r')-meta\.xml$'
        r'|-meta\.xml$|\.xml$|\.cls$|\.trigger$|\.page$|\.component$|\.resource$|\.asset$',
        '', name
    )

members_by_type = {}

def add(meta_type, member):
    if member:
        members_by_type.setdefault(meta_type, set()).add(member)

for f in changed_files:
    if "force-app/main/default/" not in f:
        continue
    parts = f.replace("force-app/main/default/", "").split("/")
    if len(parts) < 2:
        continue
    folder, filename = parts[0], parts[1]

    # Folder-based (reports, dashboards, emailTemplates, documents)
    # Standard package.xml requires: FolderType member = subFolder name
    #                                 ContentType member = subFolder/memberName
    FOLDER_TYPE_MAP = {
        "reports":        ("Report",         "ReportFolder"),
        "dashboards":     ("Dashboard",      "DashboardFolder"),
        "emailTemplates": ("EmailTemplate",  "EmailTemplateFolder"),
        "documents":      ("Document",       "DocumentFolder"),
    }
    if folder in FOLDER_TYPE_MAP:
        content_type, folder_type = FOLDER_TYPE_MAP[folder]
        if len(parts) >= 3:
            sub_folder = parts[1]
            add(folder_type, sub_folder)                                    # e.g. ReportFolder -> MyFolder
            add(content_type, f"{sub_folder}/{strip_suffix(parts[2])}")    # e.g. Report -> MyFolder/MyReport
        continue

    # objectTranslations
    if folder == "objectTranslations":
        add("CustomObjectTranslation", parts[1])
        continue

    # objects
    if folder == "objects":
        obj_name = parts[1]
        if len(parts) >= 4 and parts[2] in SUB_TYPE_MAP:
            add(SUB_TYPE_MAP[parts[2]], f"{obj_name}.{strip_suffix(parts[3])}")
        else:
            add("CustomObject", obj_name)
        continue

    # territory2Models hierarchy
    if folder == "territory2Models":
        model_name = parts[1]
        if len(parts) == 3:
            add("Territory2Model", model_name)
        elif len(parts) >= 4:
            sub = parts[2]
            member_name = strip_suffix(parts[3])
            if sub == "territory2Types":
                add("Territory2Type", f"{model_name}.{member_name}")
            elif sub == "territories":
                add("Territory2", f"{model_name}.{member_name}")
            elif sub == "territory2Rules":
                add("Territory2Rule", f"{model_name}.{member_name}")
        continue

    # Bundle types — member = bundle folder name
    if folder in BUNDLE_TYPES:
        meta_type = TYPE_MAP.get(folder)
        if meta_type:
            add(meta_type, parts[1])
        continue

    # staticresources
    if folder == "staticresources":
        if len(parts) > 2:
            continue
        if not re.search(r'(\.resource-meta\.xml|\.resource)$', filename):
            continue
        add("StaticResource", strip_suffix(filename))
        continue

    # contentassets
    if folder == "contentassets":
        if not re.search(r'(\.asset-meta\.xml|\.asset)$', filename):
            continue
        add("ContentAsset", strip_suffix(filename))
        continue

    # labels — always single member
    if folder == "labels":
        add("CustomLabels", "CustomLabels")
        continue

    # settings — member = filename without suffix
    if folder == "settings":
        add("Settings", strip_suffix(filename))
        continue

    # General flat types
    meta_type = TYPE_MAP.get(folder)
    if meta_type:
        add(meta_type, strip_suffix(filename))
    else:
        print(f"WARNING: unrecognized folder '{folder}' in path '{f}' – skipped")

if not members_by_type:
    print("WARNING: No metadata members detected – no artifacts generated")
    sys.exit(1)

out_dir = os.path.join(build_sources, "manifest")
os.makedirs(out_dir, exist_ok=True)

# package.xml
NS = "http://soap.sforce.com/2006/04/metadata"
ET.register_namespace("", NS)
root = ET.Element(f"{{{NS}}}Package")
for mtype in sorted(members_by_type):
    types_el = ET.SubElement(root, f"{{{NS}}}types")
    for m in sorted(members_by_type[mtype]):
        ET.SubElement(types_el, f"{{{NS}}}members").text = m
    ET.SubElement(types_el, f"{{{NS}}}name").text = mtype
ET.SubElement(root, f"{{{NS}}}version").text = api_version
tree = ET.ElementTree(root)
ET.indent(tree, space="    ")
pkg_path = os.path.join(build_sources, "manifest", f"{branch}_package.xml")
with open(pkg_path, "wb") as fh:
    tree.write(fh, encoding="utf-8", xml_declaration=True)
print(f"package.xml   -> {pkg_path}")

# Classify ApexClass members into test vs main
def is_test_class(name):
    lower = name.lower()
    return lower.endswith("test") or lower.endswith("tests") or lower.endswith("_test")

def has_istest_annotation(name):
    cls_path = os.path.join(build_sources, "force-app", "main", "default", "classes", f"{name}.cls")
    if not os.path.isfile(cls_path):
        return False
    try:
        with open(cls_path, "r", encoding="utf-8", errors="ignore") as fh:
            return bool(re.search(r'@isTest', fh.read(2000), re.IGNORECASE))
    except OSError:
        return False

all_apex   = members_by_type.get("ApexClass", set())
test_classes = sorted(c for c in all_apex if is_test_class(c) or has_istest_annotation(c))
main_classes = sorted(c for c in all_apex if c not in test_classes)

tc_path = os.path.join(build_sources, "manifest", f"{branch}_TestClass.txt")
if test_classes:
    with open(tc_path, "w") as fh:
        fh.write("\n".join(test_classes) + "\n")
    print(f"TestClass.txt -> {tc_path} | {test_classes}")
else:
    print("No test classes in delta – TestClass.txt skipped")

mc_path = os.path.join(build_sources, "manifest", f"{branch}_MainClass.txt")
if main_classes:
    with open(mc_path, "w") as fh:
        fh.write("\n".join(main_classes) + "\n")
    print(f"MainClass.txt -> {mc_path} | {main_classes}")
else:
    print("No main classes in delta – MainClass.txt skipped")
