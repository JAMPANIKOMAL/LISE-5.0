# LISE 5.0 - Basic Orchestrator Script (Task 1.2) - VirtualBox Edition
# This script automates the creation of the lab using VirtualBox VMs.

import time
import json
import requests

# --- CONFIGURATION ---
GNS3_SERVER_URL = "http://localhost:3080"
# IMPORTANT: Make sure these names match your VirtualBox VM templates in GNS3
RED_VM_TEMPLATE_NAME = "Kali-Red-Team"
BLUE_VM_TEMPLATE_NAME = "Kali-Blue-Team"
# --- END OF CONFIGURATION ---

# A session object will handle our connection to the GNS3 server
session = requests.Session()

def get_template_id(template_name, template_type):
    """
    Finds the ID of a template by its name and type.
    """
    response = session.get(f"{GNS3_SERVER_URL}/v2/templates")
    response.raise_for_status()
    for template in response.json():
        if template['name'] == template_name and template['template_type'] == template_type:
            return template['template_id']
    raise ValueError(f"Template '{template_name}' of type '{template_type}' not found.")

def wait_for_node_status(project_id, node_id, desired_status, timeout=180):
    """
    Waits for a specific node to reach a desired status (e.g., 'started').
    """
    print(f"  - Waiting for node to be '{desired_status}'...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = session.get(f"{GNS3_SERVER_URL}/v2/projects/{project_id}/nodes/{node_id}")
        response.raise_for_status()
        current_status = response.json()['status']
        if current_status == desired_status:
            print(f"    - Node is now '{desired_status}'.")
            return
        time.sleep(5)
    raise Exception(f"Timeout: Node did not reach status '{desired_status}' within {timeout} seconds.")

def main():
    """
    Main function to orchestrate the scenario deployment.
    """
    project_id = None
    try:
        # --- Step 1: Verify Connection ---
        print("Connecting to the GNS3 server...")
        response = session.get(f"{GNS3_SERVER_URL}/v2/version")
        response.raise_for_status()
        version = response.json()['version']
        print(f"Connected to GNS3 server version: {version}")

        # --- Step 2: Get Template IDs ---
        print("\nFetching template information...")
        red_vm_template_id = get_template_id(RED_VM_TEMPLATE_NAME, "virtualbox")
        blue_vm_template_id = get_template_id(BLUE_VM_TEMPLATE_NAME, "virtualbox")
        switch_template_id = get_template_id("Ethernet switch", "ethernet_switch")
        print(f"Found Template ID for '{RED_VM_TEMPLATE_NAME}'")
        print(f"Found Template ID for '{BLUE_VM_TEMPLATE_NAME}'")
        print("Found Template ID for 'Ethernet switch'")

        # --- Step 3: Robust Clean Up and Create Project ---
        project_name = "LISE - VirtualBox Lab 1"
        print(f"\nPreparing project: {project_name}...")
        
        response = session.get(f"{GNS3_SERVER_URL}/v2/projects")
        response.raise_for_status()
        for p in response.json():
            if p['name'] == project_name:
                print("Found an old version of the lab. Cleaning it up...")
                session.post(f"{GNS3_SERVER_URL}/v2/projects/{p['project_id']}/close")
                time.sleep(1)
                session.delete(f"{GNS3_SERVER_URL}/v2/projects/{p['project_id']}").raise_for_status()
                print("Cleanup complete.")
                time.sleep(2)
                break

        payload = {'name': project_name}
        response = session.post(f"{GNS3_SERVER_URL}/v2/projects", data=json.dumps(payload))
        response.raise_for_status()
        project_data = response.json()
        project_id = project_data['project_id']
        print(f"Successfully created project '{project_data['name']}'")

        # --- Step 4: Create Nodes ---
        print("\nDeploying virtual machines and network devices...")
        
        def create_node_from_template(p_id, name, template_id, x, y):
            url = f"{GNS3_SERVER_URL}/v2/projects/{p_id}/templates/{template_id}"
            payload = {'name': name, 'x': x, 'y': y, 'compute_id': 'local'}
            response = session.post(url, data=json.dumps(payload))
            response.raise_for_status()
            return response.json()

        switch = create_node_from_template(project_id, "Lab-Switch", switch_template_id, 0, 0)
        red_vm = create_node_from_template(project_id, "Red-Team-VM", red_vm_template_id, -200, -100)
        blue_vm = create_node_from_template(project_id, "Blue-Team-VM", blue_vm_template_id, 200, -100)
        print("Nodes deployed successfully.")

        # --- Step 5: Create Links ---
        print("\nConnecting the devices with virtual cables...")
        
        response = session.get(f"{GNS3_SERVER_URL}/v2/projects/{project_id}/nodes")
        response.raise_for_status()
        nodes = response.json()
        
        switch_id = next(n['node_id'] for n in nodes if n['name'] == 'Lab-Switch')
        red_vm_id = next(n['node_id'] for n in nodes if n['name'] == 'Red-Team-VM')
        blue_vm_id = next(n['node_id'] for n in nodes if n['name'] == 'Blue-Team-VM')

        link1_payload = { "nodes": [ {"adapter_number": 0, "node_id": red_vm_id, "port_number": 0}, {"adapter_number": 0, "node_id": switch_id, "port_number": 0} ] }
        session.post(f"{GNS3_SERVER_URL}/v2/projects/{project_id}/links", data=json.dumps(link1_payload)).raise_for_status()
        
        link2_payload = { "nodes": [ {"adapter_number": 0, "node_id": blue_vm_id, "port_number": 0}, {"adapter_number": 0, "node_id": switch_id, "port_number": 1} ] }
        session.post(f"{GNS3_SERVER_URL}/v2/projects/{project_id}/links", data=json.dumps(link2_payload)).raise_for_status()
        print("Nodes linked successfully.")

        # --- Step 6: Start the Lab Sequentially ---
        print("\nStarting the lab environment sequentially...")
        
        # Start the switch first
        print("  - Starting Lab-Switch...")
        session.post(f"{GNS3_SERVER_URL}/v2/projects/{project_id}/nodes/{switch_id}/start").raise_for_status()
        wait_for_node_status(project_id, switch_id, 'started')

        # Start the Red VM and wait for it to be ready
        print("  - Starting Red-Team-VM...")
        session.post(f"{GNS3_SERVER_URL}/v2/projects/{project_id}/nodes/{red_vm_id}/start").raise_for_status()
        wait_for_node_status(project_id, red_vm_id, 'started')

        # Start the Blue VM and wait for it to be ready
        print("  - Starting Blue-Team-VM...")
        session.post(f"{GNS3_SERVER_URL}/v2/projects/{project_id}/nodes/{blue_vm_id}/start").raise_for_status()
        wait_for_node_status(project_id, blue_vm_id, 'started')

        print("\nLab successfully deployed and all nodes started! You can now see it in GNS3.")

    except requests.exceptions.RequestException as e:
        print(f"\n--- A Connection Error Occurred ---")
        if hasattr(e, 'response') and e.response:
            print(f"Status Code: {e.response.status_code}")
            print(f"Response: {e.response.text}")
        else:
            print(f"Error: {e}")
            
    except Exception as e:
        print(f"\n--- An Unexpected Error Occurred ---")
        print(f"Error: {e}")

    finally:
        if project_id:
            print("\nClosing project session...")
            session.post(f"{GNS3_SERVER_URL}/v2/projects/{project_id}/close")
            print("Project session closed.")

if __name__ == "__main__":
    main()
