# Baxter DB15 User / Safety I/O Port Reference & Hardware Interlock Guide

*Archived and validated reference for the rear 15-pin D-Sub (DB15) Safety and User I/O connector on the Rethink Robotics Baxter Research Robot.*

---

## 1. Overview of the DB15 Port

Located on the lower back of Baxter's waist (adjacent to the AC power switch and main Ethernet RJ45 jack), the **DB15 Female Receptacle** serves as Baxter's primary **Hardware Safety Interlock** and general-purpose digital/analog I/O interface.

Baxter’s physical 48V motor power relays are hard-wired through this port. If the safety circuit is open or disconnected, the internal motor controller hardware halts all arm actuators and logs:
```text
ERROR (/realtime_loop,Joint.cpp:337) Joint torso_t0 has SEA_GLOBAL_ERROR_NO_EXTERNAL_ENABLE
WARN (/realtime_loop,RobotStatePublisher.cpp:179) Bad ESTOP state: source 4 not USER, button = 1
```

---

## 2. The Female DB15 Socket Pinout Trap

> [!CAUTION]
> **CRITICAL WIRING GOTCHA: FEMALE SOCKETS ARE NUMBERED RIGHT-TO-LEFT!**
> Standard male D-Sub connectors count Pin 1 from top-left. However, when looking directly into the **female socket holes on Baxter's chassis**, **PIN 1 is in the TOP-RIGHT corner**, and **PIN 9 is in the BOTTOM-RIGHT corner**.

```text
               TOP ROW (Wider - 8 Holes):
     [ 8 ]  [ 7 ]  [ 6 ]  [ 5 ]  [ 4 ]  [ 3 ]  [ 2 ]  [ 1 ]    <-- PIN 1 IS FAR RIGHT!
      \                                                  /
       \  [ 15 ] [ 14 ] [ 13 ] [ 12 ] [ 11 ] [ 10 ] [ 9 ]     /   <-- PIN 9 IS FAR RIGHT!
        --------------------------------------------------
                 BOTTOM ROW (Narrower - 7 Holes)
                (Looking directly into Robot Socket)
```

*(If you illuminate the socket with a flashlight, tiny embossed numbers `1`, `8`, `9`, and `15` are stamped into the corners of the black dielectric connector housing).*

---

## 3. Complete Pinout Table

| Pin # | Signal Name | Electrical Type | Description |
| :---: | :--- | :--- | :--- |
| **1** | **`+24V_OUT`** | Power Output (+24V DC, 1A max) | Internal auxiliary logic supply for safety loop and external sensors |
| **2** | `DIG_OUT_0` | Open Collector / Sinking Output | Software-controllable general digital output 0 |
| **3** | `DIG_OUT_1` | Open Collector / Sinking Output | Software-controllable general digital output 1 |
| **4** | **`TORSO_IN_0 (+)`** | **Opto-Isolated Digital Input (+)** | **Primary Safety / E-Stop Channel 0 Input** (Anode of internal optocoupler) |
| **5** | `TORSO_IN_1 (+)` | Opto-Isolated Digital Input (+) | Secondary Safety / User Digital Input 1 |
| **6** | `ANALOG_IN_0`| Analog Input (0 to +5V ADC) | General purpose analog input |
| **7** | `+5V_OUT` | Power Output (+5V DC, 500mA max) | Auxiliary +5V sensor supply |
| **8** | `GND` | Chassis / Logic Ground | Common return |
| **9** | **`GND_24V`** | **Power Ground Return (0V)** | **Ground return for internal +24V DC supply (Pin 1)** |
| **10**| `DIG_OUT_RET` | Ground / Emitter Return | Return for digital open-collector outputs |
| **11**| `TORSO_IN_0_RET (-)` | Opto-Isolated Return (-) | Alternative return connection |
| **12**| **`TORSO_IN_0_RET (-)`** | **Opto-Isolated Cathode Return (-)** | **Primary Safety / E-Stop Channel 0 Return** (Cathode of internal optocoupler) |
| **13**| `TORSO_IN_1_RET (-)`| Opto-Isolated Return (-) | Return for secondary optocoupler |
| **14**| `ANALOG_GND` | Analog Ground Reference | Clean analog ground |
| **15**| `GND` | Chassis Ground | Earth / chassis shield |

---

## 4. The Optoisolator Circuit & Why Passive Jumpers Fail

A frequent source of frustration in university and research labs is attempting to bridge the E-stop with a simple piece of wire or paperclip between `Pin 4` and `Pin 12`.

### Internal Electrical Schematic:

```text
 Baxter Internal Torso Board             External Connector (DB15)
 ---------------------------             -------------------------
  [+24V DC Internal Regulator] -----------> Pin 1 (+24V_OUT)

                                         +- [External E-Stop Switch] <-+
                                         |                             |
  Pin 4 (Torso In 0)  -------------------+                             |
       |                                                               |
     [ 1.5 kΩ Resistor ]                                               |
       |                                                               |
    +--+--+ (Anode)                                                    |
    | LED |  [Optocoupler 4N35 / PS2801]                               |
    +--+--+ (Cathode)                                                  |
       |                                                               |
  Pin 12 (Torso In 0 Return) ------------+                             |
                                         |                             |
  Pin 9 (GND) ---------------------------+-----------------------------+
```

### The Logic Inversion:
From the official Rethink Robotics Hardware Manual:
> *"Torso In is **FALSE (0)** when current is flowing through the optocoupler LED, and **TRUE (1)** otherwise. A disconnected or unpowered input registers as **TRUE (1) [ERROR / OPEN]**."*

Because the input is an optocoupler LED, **current must actively flow** through the diode to register a safe/closed state (`0`). Shorting Pin 4 to Pin 12 without supplying voltage yields 0 mA of current, leaving the LED unlit and the state at `1` (E-stop Tripped).

---

## 5. Wiring Instructions: Two Options

### Option 1: Official External E-Stop Pendant (Recommended for Safety)
Use a standard normally-closed (NC) red mushroom-head twist-to-release safety pendant:

1. Connect **Pin 1 (+24V)** to one side of the NC contact on the E-stop switch.
2. Connect the other side of the NC contact to **Pin 4** (`Torso 0 In +`).
3. Connect **Pin 12** (`Torso 0 Return -`) to **Pin 9** (`GND_24V`).

*Operation*:
- When button is **UP (Normal)**: 24V flows through the switch, lights the internal optocoupler LED, and Baxter reports `estop_button: False` (0).
- When button is **HIT (Depressed)**: Circuit opens, LED turns off, 48V motor bus immediately drops out, arms go limp safely, and Baxter reports `estop_button: True` (1).

---

### Option 2: Benchtop Bypass Plug (For Standalone Development)
If an external pendant is unavailable and you need to enable the robot for stationary testing:

```text
  Top Row:     Pin 1 (+24V)  ─────── JUMPER 1 ───────> Pin 4 (Torso In 0)
  Bottom Row:  Pin 9 (GND)    ─────── JUMPER 2 ───────> Pin 12 (Torso Return)
```

1. Insert a secure wire jumper between **Pin 1 (Top-Right)** and **Pin 4 (4th from Right)**.
2. Insert a second secure wire jumper between **Pin 9 (Bottom-Right)** and **Pin 12 (4th from Right / Center)**.

> [!CAUTION]
> **DANGER: DO NOT SHORT PIN 4 TO PIN 12!**
> Never bridge Pin 4 to Pin 12 while also connecting to Pin 1 and Pin 9. Doing so connects +24V directly to GND, causing a dead short on the internal logic power supply!
