# LISE 5.0 - Basic Frontend Web Server (Task 1.5)
# This script runs a simple web server to launch the orchestrator.

from flask import Flask, render_template, jsonify
import subprocess
import threading
import sys
import os

# Initialize the Flask application
app = Flask(__name__)

# --- Global variable to track lab status ---
lab_status = "Idle"

def run_orchestrator_script():
    """
    This function runs the orchestrator_vbox.py script in a separate process.
    It captures and prints the output in real-time.
    This function will be run in a background thread to avoid blocking the web server.
    """
    global lab_status
    try:
        lab_status = "Launching..."
        print("--- Starting Orchestrator Script ---")

        # Determine the path to the python executable
        python_executable = sys.executable
        
        # Get the directory of the current script to find the orchestrator script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        orchestrator_path = os.path.join(script_dir, "orchestrator_vbox.py")

        # Use Popen to run the script as a separate process
        process = subprocess.Popen(
            [python_executable, orchestrator_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        # Print stdout and stderr line by line in real-time
        for line in process.stdout:
            print(line, end='')
        for line in process.stderr:
            print(f"ERROR: {line}", end='')
        
        process.wait() # Wait for the process to complete

        if process.returncode == 0:
            lab_status = "Successfully Deployed"
            print("--- Orchestrator Script Finished Successfully ---")
        else:
            lab_status = "Error"
            print(f"--- Orchestrator Script Exited with Error Code: {process.returncode} ---")

    except Exception as e:
        lab_status = "Error"
        print(f"--- An exception occurred while running the orchestrator: {e} ---")


@app.route('/')
def index():
    """
    This function serves the main HTML page.
    """
    # The HTML file must be in a folder named 'templates'
    return render_template('index.html')


@app.route('/launch', methods=['POST'])
def launch_lab():
    """
    This function is triggered when the "Launch Lab" button is clicked.
    It starts the orchestrator script in a new background thread.
    """
    global lab_status
    if lab_status == "Launching...":
        return jsonify({"status": "already_running", "message": "Lab deployment is already in progress."}), 409

    # Start the orchestrator script in a new thread
    thread = threading.Thread(target=run_orchestrator_script)
    thread.daemon = True # Allows the main app to exit even if threads are running
    thread.start()
    
    return jsonify({"status": "success", "message": "Lab deployment initiated. See console for progress."})


@app.route('/status')
def status():
    """
    This function provides the current status of the lab deployment.
    The frontend can poll this endpoint to update the UI.
    """
    global lab_status
    return jsonify({"status": lab_status})


if __name__ == '__main__':
    # Run the Flask app
    # host='0.0.0.0' makes it accessible from other devices on your network
    app.run(host='0.0.0.0', port=5000, debug=True)
