import pyodbc
import numpy as np
import random
import time
import threading
from datetime import datetime

# -----------------------------
# CONFIG
# -----------------------------
SERVER = 'localhost'
DATABASE = 'IndustrialDB'
ENERGY_RATE = 8
SLEEP_TIME = 5
NUM_MACHINES = 5

running = False

# -----------------------------
# DB CONNECTION
# -----------------------------
conn = pyodbc.connect(
    'DRIVER={ODBC Driver 18 for SQL Server};'
    f'SERVER={SERVER};'
    f'DATABASE={DATABASE};'
    'Trusted_Connection=yes;'
    'TrustServerCertificate=yes;'
)
cursor = conn.cursor()

print("🏭 Enterprise Industrial System Ready")

# -----------------------------
# MACHINE TYPES
# -----------------------------
machine_types = {
    "Motor": {"base_temp": 60, "wear_rate": 0.0015},
    "Pump": {"base_temp": 55, "wear_rate": 0.0012},
    "Compressor": {"base_temp": 70, "wear_rate": 0.0018}
}

machines = {}

machine_type_list = list(machine_types.keys())

for i in range(1, NUM_MACHINES + 1):
    m_type = machine_type_list[(i-1) % len(machine_type_list)]

    machines[f"M-{i}"] = {
        "type": m_type,
        "runtime": 0,
        "wear": 0,
        "bearing_health": 100,
        "energy_kwh": 0,
        "base_voltage": 415,
        "last_failure_time": None
    }

# -----------------------------
# FAULT CLASSIFICATION ENGINE
# -----------------------------
def classify_fault(temp, vib, eff, volt):
    if temp > 100:
        return "Overheating", "Critical", 15000
    elif vib > 10:
        return "Bearing Failure", "Major", 10000
    elif eff < 70:
        return "Efficiency Loss", "Minor", 5000
    elif volt < 390:
        return "Voltage Dip", "Minor", 2000
    return None, None, None

def generate_alarm_code(severity):
    prefix = {"Critical": "CR", "Major": "MJ", "Minor": "MN"}
    return f"{prefix[severity]}-ALM-{random.randint(100,999)}"

def get_shift_load(hour):
    if 8 <= hour < 18:
        return random.uniform(75, 95)
    elif 18 <= hour < 22:
        return random.uniform(60, 75)
    else:
        return random.uniform(40, 60)

# -----------------------------
# SIMULATION LOOP
# -----------------------------
def simulation():
    global running

    while True:

        if running:

            now = datetime.now()
            hour = now.hour

            for machine_id, state in machines.items():

                config = machine_types[state["type"]]

                state["runtime"] += SLEEP_TIME / 3600
                state["wear"] += config["wear_rate"]

                load = get_shift_load(hour)
                ambient = random.uniform(28, 38)

                voltage = state["base_voltage"] + random.uniform(-8, 8)
                current = (load / 100) * random.uniform(90, 130)

                state["bearing_health"] -= state["wear"] * 2
                state["bearing_health"] = max(40, state["bearing_health"])

                vibration = 3 + (100 - state["bearing_health"]) * 0.06 + np.random.normal(0, 0.2)

                efficiency = max(65, 98 - (state["wear"] * 55))
                power_factor = max(0.75, 0.96 - state["wear"])
                frequency = 50 + random.uniform(-0.1, 0.1)

                power_kw = (voltage * current * power_factor * 1.732) / 1000

                state["energy_kwh"] += power_kw * (SLEEP_TIME / 3600)

                energy_cost = state["energy_kwh"] * ENERGY_RATE

                temperature = (
                    config["base_temp"] +
                    (load * 0.3) +
                    (state["wear"] * 60) +
                    (ambient * 0.1) +
                    np.random.normal(0, 1)
                )

                downtime = 0
                failure = 0
                fault_type = None
                severity = None
                cost = None
                alarm = None
                maintenance_id = None

                # Fault detection
                fault_type, severity, cost = classify_fault(
                    temperature, vibration, efficiency, voltage
                )

                if fault_type:

                    failure = 1
                    downtime = random.uniform(1, 4)

                    alarm = generate_alarm_code(severity)

                    # Insert maintenance event
                    cursor.execute("""
                    INSERT INTO MaintenanceEvents
                    (MachineID, MachineType, EventTimestamp,
                     FaultType, AlarmCode, SeverityLevel,
                     ActionTaken, DowntimeHours, EstimatedCost)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    machine_id,
                    state["type"],
                    now,
                    fault_type,
                    alarm,
                    severity,
                    "Component replaced / system reset",
                    downtime,
                    cost
                    )

                    # Get generated MaintenanceEventID
                    cursor.execute("SELECT SCOPE_IDENTITY()")
                    maintenance_id = cursor.fetchone()[0]

                    state["wear"] = 0
                    state["bearing_health"] = 100

                    print(f"🚨 {machine_id} | {fault_type} | {severity}")

                failure_probability = min(
                    1.0,
                    (temperature / 170) * 0.25 +
                    (vibration / 16) * 0.25 +
                    ((100 - efficiency) / 100) * 0.25 +
                    (load / 150) * 0.25
                )

                # Insert telemetry
                cursor.execute("""
                INSERT INTO MachineData
                (
                MachineID, Timestamp, Temperature, Vibration, Pressure,
                RuntimeHours, Downtime, Failure, Failure_Probability,
                Voltage, Current_A, Power_kW, Energy_KWh,
                PowerFactor, Frequency_Hz, LoadPercent,
                EfficiencyPercent, AmbientTemperature,
                Energy_Cost, MachineType,
                MaintenanceEventID, FaultType, AlarmCode
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                machine_id,
                now,
                round(temperature,2),
                round(vibration,2),
                random.uniform(18,25),
                round(state["runtime"],2),
                round(downtime,2),
                failure,
                round(failure_probability,2),
                round(voltage,2),
                round(current,2),
                round(power_kw,2),
                round(state["energy_kwh"],2),
                round(power_factor,2),
                round(frequency,2),
                round(load,2),
                round(efficiency,2),
                round(ambient,2),
                round(energy_cost,2),
                state["type"],
                maintenance_id,
                fault_type,
                alarm
                )

            conn.commit()

            print(f"✅ Batch inserted at {now}")

        time.sleep(SLEEP_TIME)

# -----------------------------
# CONTROL PANEL
# -----------------------------
def control():

    global running

    while True:

        cmd = input("Command (start / pause / stop): ").lower()

        if cmd == "start":
            running = True
            print("▶ Simulation STARTED")

        elif cmd == "pause":
            running = False
            print("⏸ Simulation PAUSED")

        elif cmd == "stop":
            running = False
            print("🛑 System STOPPED")
            conn.close()
            break

# -----------------------------
# START THREAD
# -----------------------------
threading.Thread(target=simulation, daemon=True).start()

control()