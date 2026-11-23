# Lab 1: The E-Stop Hardware Lockout & The Real-World Fix

*Demystifying Baxter's missing E-Stop, the DB15 safety port, optocoupled inputs, and the female connector pinout trap.*

---

## 1. Objectives

By the end of this lab, you will:
1. Understand why Baxter refuses to energize motor relays out of the box and how the internal safety loop works.
2. Identify the optical isolation mechanism inside Baxter's torso and understand why passive jumper wires fail.
3. Overcome the classic "Female D-Sub Mirror Pinout Trap" that leads 90% of engineers to miswire the safety port.
4. Construct either an **External Mushroom-Button Safety Pendant** or a **Benchtop 2-Wire Bypass Plug**.
5. Verify live state transitions on the `/robot/state` topic using `baxter status`.

---

## 2. The Mysterious Symptom: "Why Won't My Baxter Enable?"

When powering on Baxter in a lab for the first time, you will inevitably see:
```bash
$ baxter status
Robot Status:
  enabled: False
  stopped: True
  error: True
  estop_button: 1
  estop_source: 4
```
And inside Baxter's internal diagnostic log (`/var/log/rethink.log`):
```text
ERROR (/realtime_loop,Joint.cpp:337) Joint torso_t0 has SEA_GLOBAL_ERROR_NO_EXTERNAL_ENABLE
WARN (/realtime_loop,RobotStatePublisher.cpp:179) Bad ESTOP state: source 4 not USER, button = 1
```

### Why This Happens:
1. **Baxter has NO built-in E-stop button on its body**: Unlike industrial cobots with an integrated red button on the base or teach pendant, Baxter’s physical 48V motor power bus relies entirely on an **external safety loop connected through a 15-pin (DB15) port on the rear waist**.
2. **`source: 4`**: Indicates Baxter’s External Safety Interlock Port.
3. **`button: 1`**: Indicates the hardware circuit is **OPEN** (Power disabled).

Until current actively flows through this circuit, Baxter's internal hardware safety contactor will physically refuse to latch the 48V power relays to the arm motors.

---

## 3. The Optoisolator Trap (Why Paperclips Fail)

When engineers first discover the DB15 port, the immediate instinct is to look at the pinout, find `Pin 4 (Torso In 0)` and `Pin 12 (Torso In 0 Return)`, and shove a passive wire loop or paperclip between them.

**This will NOT work.**

### Why It Fails:
Baxter's safety inputs are **opto-isolated inputs** consisting of an internal LED inside an optical coupler (e.g. 4N35):

```text
  Baxter Torso Board                 DB15 Port Pins
  ------------------                 --------------
   +24V Supply ------------------------> Pin 1 (+24V DC Out)

   Pin 4 (Torso In 0) ──[ 1.5 kΩ ]──+
                                     │
                                   [LED] (Optocoupler)
                                     │
   Pin 12 (Torso Return) ────────────+

   Pin 9 (Ground Return) ──────────────> Pin 9 (GND)
```

From Rethink Robotics Engineering Specifications:
> *"Torso In is **FALSE (0) [SAFE]** when current is flowing through the optocoupler LED, and **TRUE (1) [ERROR / OPEN]** otherwise. A disconnected or unpowered input registers as **TRUE (1)**."*

Because it is an optocoupler diode, **current must actively flow (5V to 24V DC)** through the LED. Shorting Pin 4 to Pin 12 with a piece of wire without voltage supplies 0 Volts and 0 Amps, leaving the diode dark and the robot in a permanent E-stop trip state (`button: 1`).

---

## 4. The Female DB15 Trap: Pins Count from RIGHT to LEFT!

This is the single most common failure mode when wiring Baxter's safety connector.

> [!CAUTION]
> **MIRROR-IMAGE PINOUT ALERT:**
> Standard Male D-Sub plugs count Pin 1 from top-left. But when looking **directly into the female holes on Baxter's rear waist**, **PIN 1 is in the TOP-RIGHT corner**, NOT the top-left!

```text
               TOP ROW (Wider Row - 8 Holes):
     [ 8 ]  [ 7 ]  [ 6 ]  [ 5 ]  [ 4 ]  [ 3 ]  [ 2 ]  [ 1 ]    <-- PIN 1 IS TOP-RIGHT!
      \                                                  /
       \  [ 15 ] [ 14 ] [ 13 ] [ 12 ] [ 11 ] [ 10 ] [ 9 ]     /   <-- PIN 9 IS BOTTOM-RIGHT!
        --------------------------------------------------
               BOTTOM ROW (Narrower Row - 7 Holes)
                (Looking directly into Robot Chassis)
```

*(If you shine a phone flashlight onto the connector, you will see tiny numbers `1`, `8`, `9`, and `15` molded into the plastic at the corners).*

If you count from left to right as if reading English text:
- You will mistakenly plug your jumper into **Pin 8** instead of **Pin 1**!
- You will mistakenly plug your ground into **Pin 15** instead of **Pin 9**!
Result: No power flows, and the E-stop remains latched.

---

## 5. Wiring Solutions

### Solution A: External E-Stop Mushroom Button (Lab Safety Standard)
Use a standard industrial Emergency Stop box featuring a normally-closed (NC) red twist-to-release mushroom switch:

```text
   DB15 Pin 1 (+24V) ───────> E-Stop Terminal 1 (NC)
   DB15 Pin 4 (Torso In) <─── E-Stop Terminal 2 (NC)
   DB15 Pin 12 (Return) ─────> DB15 Pin 9 (GND)
```

1. Connect **Pin 1 (+24V, Far Top-Right)** to the NC contact on your E-stop switch.
2. Connect the other side of the NC contact to **Pin 4 (4th hole from the right on top row)**.
3. Connect **Pin 12 (4th hole from the right / dead center on bottom row)** to **Pin 9 (Far Bottom-Right GND)**.

**Safety Behavior**:
- **Button Released (Untwisted)**: 24V flows through the switch into Pin 4, powers the internal optocoupler LED to Pin 12, and returns to Pin 9 GND. Baxter detects closed safety circuit (`estop_button: 0`).
- **Button Pressed (E-Stop)**: Circuit opens, internal LED turns off, 48V motor power relays instantly de-energize, and arms safely collapse under gravity.

---

### Solution B: Benchtop 2-Wire Bypass Plug (For Rapid Prototyping)
If your lab does not have the external pendant and you need to get the robot moving for development:

```text
  Top Row:     Pin 1 (+24V)  ─────── JUMPER 1 ───────> Pin 4 (Torso In 0)
  Bottom Row:  Pin 9 (GND)    ─────── JUMPER 2 ───────> Pin 12 (Torso Return)
```

1. Insert Jumper 1 between **Pin 1** (far top-right) and **Pin 4** (4th from right, top row).
2. Insert Jumper 2 between **Pin 9** (far bottom-right) and **Pin 12** (4th from right / center, bottom row).

> [!CAUTION]
> **FATAL WIRING WARNING: NEVER SHORT PIN 4 TO PIN 12!**
> Ensure Pin 4 and Pin 12 are **completely disconnected from each other**. 
> If you bridge Pin 4 to Pin 12 while connecting them to Pin 1 (+24V) and Pin 9 (GND), you will create a **direct dead short from +24V to GND**, which can blow the internal auxiliary fuse on Baxter's logic board!

---

## 6. Live Verification

1. **Verify with Multimeter**:
   With the robot powered ON:
   - Probe between **Pin 1 (Top-Right)** and **Pin 9 (Bottom-Right)**: Should read **+24.0 VDC $(\pm 1\text{V})$**.
   - If it reads 0V, verify you are probing the right side of the connector, not the left!

2. **Verify with CLI**:
   Run the state inspector:
   ```bash
   baxter status
   ```
   *Expected Output Once Jumpered Correctly:*
   ```text
   Robot Status:
     enabled: False
     stopped: False       <-- E-Stop is now CLEARED!
     error: False
     estop_button: 0      <-- 0 = UNPRESSED / SAFE!
     estop_source: 0
     ready: False
   ```

Notice that `stopped` has transitioned from `True` to `False` and `estop_button` is `0`! 
The safety circuit is now closed. Next, in **Lab 2**, we must address arm joint limits and gravity torque lockouts before we can energize the motors.
