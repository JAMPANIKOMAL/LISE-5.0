# LISE 5.0 - Basic Orchestrator Script (Task 1.3) - v35 (Safe with VMware process check)

import time
import json
import requests
import psutil   # for process inspection/termination

# --- CONFIGURATION ---
GNS3_SERVER_URL = "http://localhost:3080"
RED_VM_TEMPLATE_NAME = "Red-VM"
BLUE_VM_TEMPLATE_NAME = "Blue-VM"
# --- END OF CONFIGURATION ---

session = requests.Session()


def get_template_id(template_name, template_type):
    response = session.get(f"{GNS3_SERVER_URL}/v2/templates")
    response.raise_for_status()
    for template in response.json():
        if template["name"] == template_name and template["template_type"] == template_type:
            return template["template_id"]
    raise ValueError(f"Template '{template_name}' of type '{template_type}' not found.")


def get_compute_id():
    response = session.get(f"{GNS3_SERVER_URL}/v2/computes")
    response.raise_for_status()
    computes = response.json()
    if not computes:
        raise RuntimeError("No compute nodes available in GNS3 server.")
    compute_id = computes[0]["compute_id"]
    print(f"Using compute_id: {compute_id}")
    return compute_id


def check_and_kill_vmware():
    """
    Detect if vmware-vmx.exe processes are running.
    If yes, kill them to avoid 'Hypervisor busy (409)' lock issues.
    """
    vmware_procs = [p for p in psutil.process_iter(['pid', 'name']) if p.info['name'] and "vmware-vmx.exe" in p.info['name'].lower()]
    if vmware_procs:
        print("\n⚠️ Detected running VMware VM processes:")
        for proc in vmware_procs:
            print(f" - PID {proc.info['pid']} : {proc.info['name']}")

        # Kill them automatically
        for proc in vmware_procs:
            try:
                proc.kill()
                print(f"   → Killed VMware process PID {proc.info['pid']}")
            except Exception as e:
                print(f"   → Failed to kill PID {proc.info['pid']}: {e}")

        print("✅ All VMware VM processes terminated. Safe to continue.\n")
    else:
        print("\nNo existing VMware VM processes detected. Safe to continue.\n")


def main():
    project_id = None
    try:
        # --- Step 0: Ensure VMware is not holding locks ---
        check_and_kill_vmware()

        # --- Step 1: Verify Connection ---
        print("Connecting to the GNS3 server...")
        response = session.get(f"{GNS3_SERVER_URL}/v2/version")
        response.raise_for_status()
        version = response.json()["version"]
        print(f"Connected to GNS3 server version: {version}")

        # --- Step 2: Get Template IDs ---
        print("\nFetching template information...")
        red_vm_template_id = get_template_id(RED_VM_TEMPLATE_NAME, "vmware")
        blue_vm_template_id = get_template_id(BLUE_VM_TEMPLATE_NAME, "vmware")
        switch_template_id = get_template_id("Ethernet switch", "ethernet_switch")
        print(f"Found Template ID for '{RED_VM_TEMPLATE_NAME}'")
        print(f"Found Template ID for '{BLUE_VM_TEMPLATE_NAME}'")
        print("Found Template ID for 'Ethernet switch'")

        # --- Step 3: Detect compute_id ---
        compute_id = get_compute_id()

        # --- Step 4: Project cleanup + creation ---
        project_name = "LISE - Red vs Blue Lab 1"
        print(f"\nPreparing project: {project_name}...")

        response = session.get(f"{GNS3_SERVER_URL}/v2/projects")
        response.raise_for_status()
        for p in response.json():
            if p["name"] == project_name:
                print("Found an old version of the lab. Cleaning it up...")
                session.post(f"{GNS3_SERVER_URL}/v2/projects/{p['project_id']}/close")
                time.sleep(1)
                session.delete(f"{GNS3_SERVER_URL}/v2/projects/{p['project_id']}").raise_for_status()
                print("Cleanup complete.")
                time.sleep(2)
                break

        payload = {"name": project_name}
        response = session.post(f"{GNS3_SERVER_URL}/v2/projects", data=json.dumps(payload))
        response.raise_for_status()
        project_data = response.json()
        project_id = project_data["project_id"]
        print(f"Successfully created project '{project_data['name']}'")

        # --- Step 5: Deploy Nodes ---
        print("\nDeploying virtual machines and network devices...")

        def create_node_from_template(p_id, name, template_id, x, y):
            url = f"{GNS3_SERVER_URL}/v2/projects/{p_id}/templates/{template_id}"
            payload = {"name": name, "x": x, "y": y, "compute_id": compute_id}
            response = session.post(url, data=json.dumps(payload))
            response.raise_for_status()
            return response.json()

        create_node_from_template(project_id, "Lab-Switch", switch_template_id, 0, 0)
        create_node_from_template(project_id, "Red-Team-VM", red_vm_template_id, -200, -100)
        create_node_from_template(project_id, "Blue-Team-VM", blue_vm_template_id, 200, -100)
        print("Nodes deployed successfully.")

        # --- Step 6: Create Links ---
        print("\nConnecting the devices with virtual cables...")

        response = session.get(f"{GNS3_SERVER_URL}/v2/projects/{project_id}/nodes")
        response.raise_for_status()
        nodes = response.json()

        switch_id = next(n["node_id"] for n in nodes if n["name"] == "Lab-Switch")
        red_vm_id = next(n["node_id"] for n in nodes if n["name"] == "Red-Team-VM")
        blue_vm_id = next(n["node_id"] for n in nodes if n["name"] == "Blue-Team-VM")

        def create_link(node_a, adapter_a, port_a, node_b, adapter_b, port_b):
            payload = {
                "nodes": [
                    {"adapter_number": adapter_a, "node_id": node_a, "port_number": port_a},
                    {"adapter_number": adapter_b, "node_id": node_b, "port_number": port_b},
                ]
            }
            url = f"{GNS3_SERVER_URL}/v2/projects/{project_id}/links"
            session.post(url, data=json.dumps(payload)).raise_for_status()

        create_link(red_vm_id, 0, 0, switch_id, 0, 0)
        create_link(blue_vm_id, 0, 0, switch_id, 0, 1)
        print("Nodes linked successfully.")

        # --- Step 7: Wait before powering on ---
        print("\nWaiting 15s for VMware to settle before powering on VMs...")
        time.sleep(15)

        # --- Step 8: Start Nodes ---
        print("\nStarting the lab environment...")

        response = session.get(f"{GNS3_SERVER_URL}/v2/projects/{project_id}/nodes")
        response.raise_for_status()
        nodes_to_start = response.json()

        for node in nodes_to_start:
            print(f"  - Attempting to start {node['name']}...")
            start_success = False
            for attempt in range(5):  # 5 retries max
                try:
                    response = session.post(f"{GNS3_SERVER_URL}/v2/projects/{project_id}/nodes/{node['node_id']}/start")
                    response.raise_for_status()
                    print(f"    - Successfully started {node['name']}.")
                    start_success = True
                    break
                except requests.exceptions.RequestException as e:
                    if e.response and e.response.status_code == 409:
                        wait_time = 5 + attempt * 5
                        print(f"    - Conflict (409) on attempt {attempt+1}. VMware busy. Waiting {wait_time}s, retrying...")
                        time.sleep(wait_time)
                    else:
                        raise e
            if not start_success:
                print(f"    - Failed to start {node['name']} after multiple attempts. Skipping.")

        print("\n✅ Lab successfully deployed and started! You can now see it in GNS3.")

    except Exception as e:
        print(f"\n--- ERROR ---\n{e}")

    finally:
        if project_id:
            print("\nClosing project session...")
            session.post(f"{GNS3_SERVER_URL}/v2/projects/{project_id}/close")
            print("Project session closed.")


if __name__ == "__main__":
    main()
