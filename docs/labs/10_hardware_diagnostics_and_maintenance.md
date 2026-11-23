# Lab 10: Hardware Diagnostics, Maintenance & Log Retrieval

*Routine maintenance procedures, sensor tare, Zero-G calibration, FTP log analysis, and system error dictionaries.*

---

## 1. Objectives

By the end of this lab, you will:
1. Perform routine **Tare** and **Sensor Calibration** to eliminate joint drift and SEA spring bias.
2. Calibrate and test the Zero-Gravity rubber cuff sensors.
3. Access Baxter's onboard Linux filesystem over FTP to extract diagnostic logs (`/var/log/rethink.log`).
4. Decode common hardware error messages (`SEA_GLOBAL_ERROR`, `BAD_ESTOP_STATE`, `MOTOR_FAULT`).
5. Establish a laboratory maintenance schedule to keep Baxter running reliably for years.

---

## 2. Sensor Drift & Series Elastic Actuator Tare

Over weeks of continuous operation, thermal expansion and mechanical strain cause minor drift in the analog torque sensors and position encoders of Baxter's Series Elastic Actuators (SEAs). If left uncalibrated, the arms may slowly droop or feel "heavy" in Zero-G mode.

### A. The Tare Routine (Weekly Maintenance)
A **Tare** measures the zero-torque resting bias of each joint spring under known gravity configurations.
- Frequency: Approximately once per week with regular laboratory use.
- Duration: ~2 minutes.
- Procedure:
  Ensure the arms are completely unloaded (no heavy custom tools attached). Command Baxter to execute a tare cycle:
  ```bash
  # Via baxter-py or ROS command
  baxter reset
  baxter untuck
  ```

### B. Full Arm Sensor Calibration (Monthly Maintenance)
If joint angles report offsets exceeding $2^\circ$ or motors feel jerky:
- Frequency: Monthly.
- Runs a multi-pose kinematic self-test across all 14 arm joints to recalibrate spring stiffness parameters and encoder offsets.

---

## 3. Calibrating the Zero-G Rubber Cuff Sensors

Each wrist contains a pressure-sensitive conductive rubber ring:
- When squeezed, the resistance drops below a threshold, publishing `state: 1` to:
  ```text
  /robot/digital_io/<side>_lower_cuff_button/state
  ```
- If the cuff becomes unresponsive:
  1. Inspect the rubber ring for physical tears or debris lodged under the lip.
  2. Test the digital signal live using Python:
     ```python
     # Squeeze cuff and observe state transition
     async with Baxter() as robot:
         async for state in robot.subscribe("/robot/digital_io/left_lower_cuff_button/state"):
             print("Cuff Pressed:", state.get("state") == 1)
     ```

---

## 4. Extracting Internal Diagnostic Logs via FTP

Baxter runs an embedded FTP server on port 21 of its Ethernet interface (`ftp://<ip>`).

### How to Access:
- **Host**: Baxter's IP address (e.g. `169.254.9.243`)
- **Port**: `21`
- **Username**: `anonymous` (or blank)
- **Password**: *(leave blank)*

### Key Log Files to Retrieve:
1. `/var/log/rethink.log`: The primary realtime control log. Contains motor controller faults, safety interlock events, and hardware fault stack traces.
2. `/var/log/syslog`: Ubuntu kernel and system daemon events.
3. `/var/log/upstart/`: Startup logs for individual Baxter subsystems (`realtime_loop`, `camera_manager`, `display_manager`).

### Using Command-Line `curl` or `wget` to Fetch Logs:
```bash
# Download rethink.log directly from Baxter
curl -o baxter_rethink.log ftp://169.254.9.243/var/log/rethink.log
```

---

## 5. Comprehensive Error Code Dictionary

| Error Message | Root Cause | Immediate Resolution |
| :--- | :--- | :--- |
| **`SEA_GLOBAL_ERROR_NO_EXTERNAL_ENABLE`** | Rear DB15 safety circuit is open or unpowered. | Check DB15 wiring (Pin 1 to Pin 4, Pin 12 to Pin 9). Ensure +24V is present. (See Lab 1). |
| **`Bad ESTOP state: source 4, button = 1`** | Safety loop disconnected or mushroom button pressed. | Twist/release mushroom button; inspect DB15 jumper pins. (See Lab 1). |
| **`Joint right_e0 tripped mechanical joint limit`** | Twist joint jammed against physical $\pm 175^\circ$ hard stop. | Manually rotate forearm/bicep into safe central zone. (See Lab 2). |
| **`GlobalEnable requested, robot is still resetting`** | Enable attempted while error flag is active. | Execute 3-step handshake: Disable $\rightarrow$ Reset $\rightarrow$ Enable. (See Lab 3). |
| **`Bandwidth error opening camera`** | More than two cameras opened simultaneously. | Close idle hand camera before opening head camera. (See Lab 6). |
| **`Spring deflection limit exceeded`** | High acceleration or arm impacted external obstacle. | Reduce trajectory acceleration; verify workspace is clear. (See Lab 4). |

---

## 6. Preventive Maintenance Schedule

| Maintenance Task | Recommended Interval | Description |
| :--- | :---: | :--- |
| **Air Intake Filter Cleaning** | Every 3 Months | Remove and vacuum the cooling fan foam dust filters on the lower rear torso. |
| **Cable Harness Inspection** | Monthly | Inspect external spiral-wrapped cable bundles at elbows and shoulders for pinching or chafing. |
| **Joint Tare** | Weekly | Re-zero SEA torsion spring bias in operational neutral posture. |
| **Emergency Stop Inspection**| Before Every Session | Verify mushroom switch cuts motor power immediately and halts motion safely. |
