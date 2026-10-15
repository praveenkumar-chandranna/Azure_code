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
    "classes": "ApexClass", "triggers": "ApexTrigger",
    "lwc": "LightningComponentBundle", "aura": "AuraDefinitionBundle",
    "pages": "ApexPage", "components": "ApexComponent",
    "flows": "Flow", "objects": "CustomObject", "layouts": "Layout",
    "permissionsets": "PermissionSet", "profiles": "Profile",
    "staticresources": "StaticResource", "tabs": "CustomTab",
    "labels": "CustomLabels", "flexipages": "FlexiPage",
    "workflows": "Workflow", "assignmentRules": "AssignmentRules",
    "autoResponseRules": "AutoResponseRules", "escalationRules": "EscalationRules",
    "queues": "Queue", "groups": "Group", "roles": "Role",
    "reports": "Report", "dashboards": "Dashboard",
    "emailTemplates": "EmailTemplate", "messageChannels": "LightningMessageChannel",
    "customMetadata": "CustomMetadata", "namedCredentials": "NamedCredential",
    "globalValueSets": "GlobalValueSet", "duplicateRules": "DuplicateRule",
    "matchingRules": "MatchingRules", "sharingRules": "SharingRules",
    "pathAssistants": "PathAssistant", "quickActions": "QuickAction",
    "approvalProcesses": "ApprovalProcess",
}
SUB_TYPE_MAP = {
    "fields": "CustomField", "validationRules": "ValidationRule",
    "recordTypes": "RecordType", "listViews": "ListView",
    "webLinks": "WebLink", "compactLayouts": "CompactLayout",
    "fieldSets": "FieldSet", "businessProcesses": "BusinessProcess",
}

members_by_type = {}
for f in changed_files:
    if "force-app/main/default/" not in f:
        continue
    parts = f.replace("force-app/main/default/", "").split("/")
    if len(parts) < 2:
        continue
    folder, filename = parts[0], parts[1]
    meta_type = TYPE_MAP.get(folder)
    if not meta_type:
        continue
    # Static resources: only the -meta.xml descriptor or bare .resource file counts.
    # Skip inner asset files (any extension) nested inside a resource folder,
    # and skip flat asset files (.png, .zip, .js, etc.) that sit alongside the descriptor.
    if folder == "staticresources":
        if len(parts) > 2:
            continue  # nested asset inside resource folder
        if not re.search(r'(\.resource-meta\.xml|\.resource)$', filename):
            continue  # flat asset file (e.g. MyResource.png, MyResource.zip)
    member = re.sub(r'\.[a-zA-Z]+-meta\.xml$|-meta\.xml$|\.xml$|\.cls$|\.trigger$|\.page$|\.component$|\.resource$', '', filename)
    if folder in ("lwc", "aura"):
        member = parts[1]
    if folder == "objects" and len(parts) >= 4 and parts[2] in SUB_TYPE_MAP:
        member    = f"{parts[1]}.{re.sub(r'\.[a-zA-Z]+-meta\.xml$|(-meta)?\.xml$', '', parts[3])}"
        meta_type = SUB_TYPE_MAP[parts[2]]
    elif folder == "objects":
        member = parts[1]
    if member:
        members_by_type.setdefault(meta_type, set()).add(member)

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
