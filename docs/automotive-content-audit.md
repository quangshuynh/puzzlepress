# Automotive Word Search: content audit

A review aid for the 60-puzzle production book in
[`books/automotive`](../books/automotive/book.yaml), so the content can be checked
without opening every YAML entry. It reports what the sources contain and what
PuzzlePress verified. **No person has reviewed or approved this content yet**;
this document is not an editorial approval. The tables are tested against
`book.yaml` (`tests/test_automotive_audit.py`), so they cannot drift from the book.

## Status at a glance

| Item | State |
| --- | --- |
| Puzzles | 60 (Engines & Powertrains 10, Maintenance & Repair 10, Tools & Workshop 8, Vehicle Systems 10, Motorsport 8, Automotive History 6, Driving & Road Culture 8) |
| Levels | Warm-up 1-20 (13 x 13, 10-11 words), Standard 21-40 (15 x 15, 13-14 words), Challenge 41-60 (17 x 17, 16 words) |
| Words | 793 placements, 787 distinct; 6 words appear twice, none more |
| Generation | All 60 generated; every placement independently verified |
| Quality | No findings: no accidental extra targets, no screened words, no reuse above 2, no similar word sets |
| Provenance | Every word, title and matter text was drafted with an AI model (`ai_generated`) |
| External sources | None consulted for vocabulary; no source is cited for any word |
| Human review | Not done (planning question `q-vocabulary-review` is open) |
| Plan | Matches `book.yaml` with no deviation (`puzzlepress plan production`); plan not approved |

## Vocabulary provenance

All vocabulary is AI-generated and recorded as `ai_generated` in
[`planning.yaml`](../books/automotive/planning.yaml). Editing does not change that:
KDP's content guidelines define AI-generated content as created by an AI-based
tool "even if you applied substantial edits afterwards".

- **Interval 11 candidates:** 184 entries (178 distinct search forms) drafted with an
  AI model for the demonstration plan. 168 distinct forms are used.
- **Added in Interval 12:** 623 words, drafted with an AI model for this book. Each
  carries the note `Added in Interval 12.` in `planning.yaml`. All are used.
- **Edited:** `GLOVEBOX` is displayed as `GLOVE BOX` (same search form).
- **No external research:** spellings and meanings come from the model's general
  knowledge of common automotive terminology, not from a cited reference. Nothing
  was copied from another puzzle book. Generic terms only; no brand, model, team
  or driver names.

### Interval 11 candidates not used

| Candidate | Reason |
| --- | --- |
| INTAKE MANIFOLD | 14 letters do not fit the 13 x 13 warm-up fuel-and-air puzzle; PLENUM is used there |
| TOOLBOX | The first tools puzzle is titled In the Toolbox; TOOL CHEST is used |
| ABS | An acronym of 3 letters, below the plan's 4-letter minimum; short words also repeat by chance |
| EXHAUST | EXHAUST MANIFOLD is in the exhaust puzzle and contains it (an accidental extra target) |
| CATALYTIC CONVERTER | 18 letters fit no level's grid; CATALYST is used |
| SENSOR | Contained in OXYGEN SENSOR, SPEED SENSOR and similar targets |
| KART | Contained in GO KART and KARTING |
| HORSELESS CARRIAGE | 17 letters exceed the plan's 15-letter maximum |
| MIRROR | Contained in SIDE MIRROR and CHECK MIRRORS |
| GRID | Replaced in Race Day after screening (below); STARTING GRID contains it |

Candidates listed in two pools (for example BATTERY, SPARK PLUG, RADIATOR) count
once per pool; several are used under the other theme, as noted in `planning.yaml`.

## Reuse

Six words appear in two puzzles each; the configured limit is 2:
BATTERY (Service Day, Electrical System), BATTERY PACK (Diesel and Hybrid,
Electric Powertrains), CAMSHAFT (Under the Hood, Valvetrain), INVERTER (Diesel and
Hybrid, Electric Powertrains), RADIATOR (Service Day, Climate Control), TORQUE
(Under the Hood, Specs and Layouts). No two puzzles share more than two words.

## Quality screening and revisions

`word_search.quality.prohibited_words` holds a screening list of 23 offensive words
that random filler letters must never spell, added in Interval 12 for your review.
Matches are findings, never repaired. The first generation flagged ten grids. Each
was revised deliberately in its authored word list; the change and the word found
are noted on the puzzle in `planning.yaml`:

| Puzzle | Revision | Found in the grid |
| --- | --- | --- |
| Race Day | ROLL CAGE replaced GRID | PISS |
| Tire Care | INFLATOR removed | PORN |
| The Drivetrain | RING GEAR added | TITS |
| Fluids and Filters | FLUID LEVEL replaced TOP UP | FAG |
| The Brake System | STOPPING POWER replaced FRICTION | FAG |
| Officials and Flags | PROTEST added | FAG |
| Cooling System Care | RESERVOIR added | FAG, TWAT |
| Climate Control | VENTILATION replaced BLEND DOOR | PORN |
| Driver Assistance | DRIVER MONITOR replaced RADAR | FAG |
| Life in the Paddock | DEBRIEF replaced SIMULATOR | TWAT |

Generation is unchanged and deterministic. In generation v1 the random sequence
depends on the number of words, not on which words they are, so a revision that
keeps the count and word lengths barely moves a grid; revisions changed a length
or the count. Word lists are printed in alphabetical order (a deliberate editorial
choice made before screening), which also fixes generation order. Screening is
literal letter matching; it is not a full moderation of every sequence a reader
might notice.

## Editorial questions for the author

1. Review every word list for accuracy and suitability (`q-vocabulary-review`). Terms
   worth a specialist's look: SHOOTING BRAKE, HEAD UP DISPLAY (also written
   heads-up), PREIGNITION (often pre-ignition), THREE ON THE TREE, BIAS PLY,
   SIX VOLT, AM RADIO, GYMKHANA, CONCOURS, SCRUTINEERING, THRUST ANGLE.
2. Car-culture slang (GARAGE QUEEN, SLEEPER, BARN FIND, LOWRIDER) suits enthusiasts
   but may puzzle students; keep or replace.
3. American English throughout (TIRE, VISE, LICENSE, GAS STATION, INTERSTATE,
   CHECKERED FLAG). Confirm the intended market.
4. Classic Body Styles sits under Automotive History, as planned; confirm the theme fits.
5. The subtitle "60 Themed Puzzles with Solutions" and the matter text are working
   drafts. The copyright page states facts only; add your own notice, and decide
   author, imprint, ISBN and edition.
6. Review the screening list itself (`word_search.quality.prohibited_words`).
7. Decide the AI disclosure in Publishing with the provenance above.

## Puzzles

Page numbers are the printed folios (puzzle N is on page N). Grid sizes come from
the level profiles; quality is from the generated batch.

| Page | ID | Title | Theme | Level | Grid | Words | Quality |
| ---: | --- | --- | --- | --- | --- | ---: | --- |
| 1 | `engines-01` | Under the Hood | Engines & Powertrains | Warm-up | 13 x 13 | 10 | clean |
| 2 | `maintenance-01` | Service Day | Maintenance & Repair | Warm-up | 13 x 13 | 10 | clean |
| 3 | `tools-01` | In the Toolbox | Tools & Workshop | Warm-up | 13 x 13 | 10 | clean |
| 4 | `systems-01` | Stop and Steer | Vehicle Systems | Warm-up | 13 x 13 | 10 | clean |
| 5 | `motorsport-01` | Race Day | Motorsport | Warm-up | 13 x 13 | 10 | clean |
| 6 | `history-01` | Early Motoring | Automotive History | Warm-up | 13 x 13 | 10 | clean |
| 7 | `driving-01` | Open Road | Driving & Road Culture | Warm-up | 13 x 13 | 10 | clean |
| 8 | `engines-02` | Fuel, Air and Spark | Engines & Powertrains | Warm-up | 13 x 13 | 11 | clean |
| 9 | `maintenance-02` | Tire Care | Maintenance & Repair | Warm-up | 13 x 13 | 10 | clean |
| 10 | `tools-02` | Measuring Up | Tools & Workshop | Warm-up | 13 x 13 | 10 | clean |
| 11 | `systems-02` | Electrical System | Vehicle Systems | Warm-up | 13 x 13 | 11 | clean |
| 12 | `motorsport-02` | On the Track | Motorsport | Warm-up | 13 x 13 | 11 | clean |
| 13 | `history-02` | Classic Body Styles | Automotive History | Warm-up | 13 x 13 | 11 | clean |
| 14 | `driving-02` | Behind the Wheel | Driving & Road Culture | Warm-up | 13 x 13 | 11 | clean |
| 15 | `engines-03` | The Drivetrain | Engines & Powertrains | Warm-up | 13 x 13 | 11 | clean |
| 16 | `maintenance-03` | Fluids and Filters | Maintenance & Repair | Warm-up | 13 x 13 | 11 | clean |
| 17 | `tools-03` | Lifting and Safety | Tools & Workshop | Warm-up | 13 x 13 | 11 | clean |
| 18 | `systems-03` | The Fuel System | Vehicle Systems | Warm-up | 13 x 13 | 11 | clean |
| 19 | `motorsport-03` | Racing Machines | Motorsport | Warm-up | 13 x 13 | 11 | clean |
| 20 | `maintenance-04` | Brake Service | Maintenance & Repair | Warm-up | 13 x 13 | 11 | clean |
| 21 | `engines-04` | Valvetrain | Engines & Powertrains | Standard | 15 x 15 | 13 | clean |
| 22 | `maintenance-05` | Scheduled Maintenance | Maintenance & Repair | Standard | 15 x 15 | 13 | clean |
| 23 | `tools-04` | Power Tools | Tools & Workshop | Standard | 15 x 15 | 13 | clean |
| 24 | `systems-04` | The Brake System | Vehicle Systems | Standard | 15 x 15 | 13 | clean |
| 25 | `motorsport-04` | Pit Lane | Motorsport | Standard | 15 x 15 | 13 | clean |
| 26 | `history-03` | Milestones of the Motor Age | Automotive History | Standard | 15 x 15 | 13 | clean |
| 27 | `driving-03` | Road Signs and Rules | Driving & Road Culture | Standard | 15 x 15 | 13 | clean |
| 28 | `engines-05` | Forced Induction | Engines & Powertrains | Standard | 15 x 15 | 13 | clean |
| 29 | `maintenance-06` | Diagnosing Trouble | Maintenance & Repair | Standard | 15 x 15 | 13 | clean |
| 30 | `tools-05` | At the Hand Tool Bench | Tools & Workshop | Standard | 15 x 15 | 13 | clean |
| 31 | `systems-05` | Steering and Suspension | Vehicle Systems | Standard | 15 x 15 | 13 | clean |
| 32 | `motorsport-05` | Officials and Flags | Motorsport | Standard | 15 x 15 | 14 | clean |
| 33 | `history-04` | Classic Car Culture | Automotive History | Standard | 15 x 15 | 13 | clean |
| 34 | `driving-04` | Car Culture | Driving & Road Culture | Standard | 15 x 15 | 13 | clean |
| 35 | `engines-06` | Diesel and Hybrid | Engines & Powertrains | Standard | 15 x 15 | 13 | clean |
| 36 | `maintenance-07` | Cooling System Care | Maintenance & Repair | Standard | 15 x 15 | 14 | clean |
| 37 | `tools-06` | The Home Garage | Tools & Workshop | Standard | 15 x 15 | 13 | clean |
| 38 | `systems-06` | Climate Control | Vehicle Systems | Standard | 15 x 15 | 13 | clean |
| 39 | `systems-07` | The Exhaust System | Vehicle Systems | Standard | 15 x 15 | 13 | clean |
| 40 | `driving-05` | Highway Travel | Driving & Road Culture | Standard | 15 x 15 | 13 | clean |
| 41 | `engines-07` | Inside the Block | Engines & Powertrains | Challenge | 17 x 17 | 16 | clean |
| 42 | `maintenance-08` | Body and Paint Care | Maintenance & Repair | Challenge | 17 x 17 | 16 | clean |
| 43 | `tools-07` | Specialty Tools | Tools & Workshop | Challenge | 17 x 17 | 16 | clean |
| 44 | `systems-08` | Driver Assistance | Vehicle Systems | Challenge | 17 x 17 | 16 | clean |
| 45 | `motorsport-06` | Racing Disciplines | Motorsport | Challenge | 17 x 17 | 16 | clean |
| 46 | `history-05` | From Workshop to Factory | Automotive History | Challenge | 17 x 17 | 16 | clean |
| 47 | `driving-06` | Learning to Drive | Driving & Road Culture | Challenge | 17 x 17 | 16 | clean |
| 48 | `engines-08` | Specs and Layouts | Engines & Powertrains | Challenge | 17 x 17 | 16 | clean |
| 49 | `maintenance-09` | Electrical Repairs | Maintenance & Repair | Challenge | 17 x 17 | 16 | clean |
| 50 | `tools-08` | Nuts, Bolts and Fasteners | Tools & Workshop | Challenge | 17 x 17 | 16 | clean |
| 51 | `systems-09` | Vehicle Electronics | Vehicle Systems | Challenge | 17 x 17 | 16 | clean |
| 52 | `motorsport-07` | Aerodynamics and Setup | Motorsport | Challenge | 17 x 17 | 16 | clean |
| 53 | `history-06` | Vintage Technology | Automotive History | Challenge | 17 x 17 | 16 | clean |
| 54 | `driving-07` | Road Trip Essentials | Driving & Road Culture | Challenge | 17 x 17 | 16 | clean |
| 55 | `engines-09` | Electric Powertrains | Engines & Powertrains | Challenge | 17 x 17 | 16 | clean |
| 56 | `maintenance-10` | Suspension and Steering Repair | Maintenance & Repair | Challenge | 17 x 17 | 16 | clean |
| 57 | `systems-10` | Wheels, Tires and Chassis | Vehicle Systems | Challenge | 17 x 17 | 16 | clean |
| 58 | `motorsport-08` | Life in the Paddock | Motorsport | Challenge | 17 x 17 | 16 | clean |
| 59 | `driving-08` | Weather and Road Skills | Driving & Road Culture | Challenge | 17 x 17 | 16 | clean |
| 60 | `engines-10` | Timing and Ignition | Engines & Powertrains | Challenge | 17 x 17 | 16 | clean |

## Word lists

As printed, alphabetical by search form.

- **1. Under the Hood** (`engines-01`): AXLE, CAMSHAFT, CRANKSHAFT, CYLINDER, FLYWHEEL, PISTON, SPARK PLUG, TIMING BELT, TORQUE, VALVE
- **2. Service Day** (`maintenance-01`): AIR FILTER, BATTERY, BRAKE FLUID, COOLANT, GASKET, INSPECTION, OIL CHANGE, OIL FILTER, RADIATOR, WIPER BLADES
- **3. In the Toolbox** (`tools-01`): CREEPER, FLOOR JACK, FUNNEL, HAMMER, PLIERS, RATCHET, SCREWDRIVER, SOCKET, VISE, WRENCH
- **4. Stop and Steer** (`systems-01`): ALTERNATOR, BRAKES, CALIPER, COIL SPRING, FUSE, STARTER, STEERING, STRUT, SUSPENSION, SWAY BAR
- **5. Race Day** (`motorsport-01`): APEX, CHICANE, HAIRPIN, HELMET, PADDOCK, PIT STOP, RACETRACK, RALLY, ROLL CAGE, SPOILER
- **6. Early Motoring** (`history-01`): ASSEMBLY LINE, CARBURETOR, COUPE, HAND CRANK, PATENT, PROTOTYPE, ROADSTER, RUNNING BOARD, SEDAN, STEAM CAR
- **7. Open Road** (`driving-01`): CAR WASH, DETOUR, HIGHWAY, MERGE, MOTEL, ODOMETER, ROAD TRIP, ROUNDABOUT, SEAT BELT, SPEED LIMIT
- **8. Fuel, Air and Spark** (`engines-02`): AIR INTAKE, COMBUSTION, COMPRESSION, DISTRIBUTOR, FUEL INJECTOR, FUEL RAIL, IGNITION COIL, MIXTURE, OCTANE, PLENUM, THROTTLE BODY
- **9. Tire Care** (`maintenance-02`): BALANCING, LUG NUTS, PATCH KIT, PUNCTURE, SIDEWALL, SPARE TIRE, TIRE PRESSURE, TIRE ROTATION, TREAD DEPTH, VALVE STEM
- **10. Measuring Up** (`tools-02`): DEPTH GAUGE, DIAL INDICATOR, FEELER GAUGE, MICROMETER, MULTIMETER, SPIRIT LEVEL, STRAIGHTEDGE, TAPE MEASURE, TIRE GAUGE, TORQUE WRENCH
- **11. Electrical System** (`systems-02`): BATTERY, CIRCUIT, DOME LIGHT, GROUND WIRE, HEADLIGHT, POWER WINDOW, RELAY, SOLENOID, STARTER MOTOR, TAILLIGHT, WIRING HARNESS
- **12. On the Track** (`motorsport-02`): BRAKING ZONE, CHECKERED FLAG, CORNER, FASTEST LAP, FORMATION LAP, OVERTAKE, POLE POSITION, RACING LINE, SLIPSTREAM, STARTING GRID, STRAIGHTAWAY
- **13. Classic Body Styles** (`history-02`): CABRIOLET, CONVERTIBLE, FASTBACK, HARDTOP, HATCHBACK, LIMOUSINE, MINIVAN, PANEL VAN, PICKUP TRUCK, SHOOTING BRAKE, STATION WAGON
- **14. Behind the Wheel** (`driving-02`): CUP HOLDER, DASHBOARD, GEAR SHIFT, GLOVE BOX, HAZARD LIGHTS, HEADREST, SIDE MIRROR, SPEEDOMETER, SUN VISOR, TACHOMETER, TURN SIGNAL
- **15. The Drivetrain** (`engines-03`): CLUTCH, DIFFERENTIAL, DRIVESHAFT, GEARBOX, GEAR RATIO, HALF SHAFT, NEUTRAL, OVERDRIVE, RING GEAR, TRANSFER CASE, TRANSMISSION
- **16. Fluids and Filters** (`maintenance-03`): ANTIFREEZE, CABIN FILTER, DRAIN PLUG, FLUID LEVEL, FUEL FILTER, GEAR OIL, GREASE, LUBRICANT, MOTOR OIL, VISCOSITY, WASHER FLUID
- **17. Lifting and Safety** (`tools-03`): BOTTLE JACK, CAR RAMPS, EAR PROTECTION, ENGINE HOIST, FIRST AID KIT, GLOVES, JACK STANDS, KNEE PADS, RESPIRATOR, SAFETY GLASSES, WHEEL CHOCKS
- **18. The Fuel System** (`systems-03`): FILLER NECK, FUEL GAUGE, FUEL LINE, FUEL PRESSURE, FUEL PUMP, FUEL TANK, GAS CAP, RETURN LINE, SENDING UNIT, TANK STRAP, VAPOR CANISTER
- **19. Racing Machines** (`motorsport-03`): DRAGSTER, DUNE BUGGY, FUNNY CAR, GO KART, MONSTER TRUCK, OPEN WHEEL, RALLY CAR, SPORTS CAR, SPRINT CAR, STOCK CAR, TOURING CAR
- **20. Brake Service** (`maintenance-04`): BLEEDING, BRAKE CLEANER, BRAKE DRUM, BRAKE LINES, BRAKE PADS, BRAKE SHOES, CALIPER PINS, RESURFACING, ROTORS, SQUEAL, WEAR SENSOR
- **21. Valvetrain** (`engines-04`): CAM LOBE, CAMSHAFT, CYLINDER HEAD, HEAD GASKET, INTAKE VALVE, LIFTER, OVERHEAD CAM, PUSHROD, ROCKER ARM, TAPPET, TIMING CHAIN, VALVE SEAT, VALVE SPRING
- **22. Scheduled Maintenance** (`maintenance-05`): BELT TENSIONER, CHECKLIST, FLUID CHECK, HOSE CLAMPS, MAINTENANCE LOG, MILEAGE, RECALL, SEASONAL, SERPENTINE BELT, SERVICE INTERVAL, SERVICE MANUAL, TUNE UP, WARRANTY
- **23. Power Tools** (`tools-04`): AIR COMPRESSOR, AIR HOSE, AIR RATCHET, ANGLE GRINDER, BENCH GRINDER, CORDLESS DRILL, DIE GRINDER, DRILL PRESS, HEAT GUN, IMPACT DRIVER, IMPACT WRENCH, ORBITAL SANDER, POLISHER
- **24. The Brake System** (`systems-04`): ANTILOCK BRAKES, BLEEDER VALVE, BRAKE BOOSTER, BRAKE LIGHT, BRAKE PEDAL, CALIPER PISTON, DISC BRAKE, DRUM BRAKE, HYDRAULIC, MASTER CYLINDER, PARKING BRAKE, STOPPING POWER, WHEEL CYLINDER
- **25. Pit Lane** (`motorsport-04`): AIR JACK, CREW CHIEF, PIT BOARD, PIT CREW, PIT LANE, PIT WALL, RADIO, REFUEL, STINT, STRATEGY, TIRE CHANGE, UNDERCUT, WHEEL GUN
- **26. Milestones of the Motor Age** (`history-03`): ACETYLENE LAMP, COACHBUILDER, ELECTRIC STARTER, FUEL INJECTION, HEADLAMP, MASS PRODUCTION, MODEL YEAR, OVERHEAD VALVE, PNEUMATIC TIRE, SYNCHROMESH, UNLEADED, VULCANIZED, WINDSHIELD WIPER
- **27. Road Signs and Rules** (`driving-03`): CENTER LINE, CROSSWALK, INTERSECTION, LANE, NO PASSING, ONE WAY, RIGHT OF WAY, SCHOOL ZONE, SHOULDER, SPEED BUMP, STOP SIGN, TRAFFIC LIGHT, YIELD
- **28. Forced Induction** (`engines-05`): BLOW OFF VALVE, BOOST PRESSURE, BYPASS VALVE, CHARGE PIPE, IMPELLER, INTERCOOLER, SPOOL, SUPERCHARGER, TURBINE, TURBOCHARGER, TURBO LAG, TWIN SCROLL, WASTEGATE
- **29. Diagnosing Trouble** (`maintenance-06`): CHECK ENGINE, CODE READER, DIAGNOSTICS, FAULT CODE, HESITATION, MISFIRE, OVERHEATING, ROUGH IDLE, SCAN TOOL, STALLING, TEST DRIVE, VACUUM LEAK, VIBRATION
- **30. At the Hand Tool Bench** (`tools-05`): BALL PEEN, BREAKER BAR, CHISEL, EXTENSION BAR, HACKSAW, HEX KEY, LOCKING PLIERS, MAGNETIC PICKUP, MALLET, NUT DRIVER, PICK SET, PRY BAR, WIRE STRIPPER
- **31. Steering and Suspension** (`systems-05`): AIR SUSPENSION, DAMPER, KNUCKLE, LEAF SPRING, POWER STEERING, RACK AND PINION, RIDE HEIGHT, SHOCK ABSORBER, STABILIZER, STEERING COLUMN, TIE ROD, TORSION BAR, TRAILING ARM
- **32. Officials and Flags** (`motorsport-05`): BLACK FLAG, BLUE FLAG, DISQUALIFIED, DRIVE THROUGH, MARSHAL, PENALTY, PROTEST, RACE CONTROL, RED FLAG, SAFETY CAR, SCRUTINEERING, STEWARD, STOP AND GO, YELLOW FLAG
- **33. Classic Car Culture** (`history-04`): BARN FIND, BENCH SEAT, CHROME, CLASSIC CAR, COLUMN SHIFT, CONCOURS, HOOD ORNAMENT, MATCHING NUMBERS, PATINA, RESTORATION, TAILFINS, VINTAGE, WHITEWALL TIRES
- **34. Car Culture** (`driving-04`): CAR CLUB, CAR SHOW, CRUISE NIGHT, DAILY DRIVER, DRIVE IN, GARAGE QUEEN, HOT ROD, LOWRIDER, MEET UP, PROJECT CAR, SHOW AND SHINE, SLEEPER, SWAP MEET
- **35. Diesel and Hybrid** (`engines-06`): BATTERY PACK, CHARGING PORT, COMMON RAIL, DIESEL, ELECTRIC MOTOR, GENERATOR, GLOW PLUG, HYBRID, INJECTION PUMP, INVERTER, KILOWATT, PLUG IN, RANGE EXTENDER
- **36. Cooling System Care** (`maintenance-07`): BLEED SCREW, COOLANT FLUSH, COOLING FAN, CORROSION, EXPANSION TANK, FAN CLUTCH, HEATER CORE, OVERFLOW, PRESSURE TEST, RADIATOR CAP, RESERVOIR, THERMOSTAT, UPPER HOSE, WATER PUMP
- **37. The Home Garage** (`tools-06`): EXTENSION CORD, FLASHLIGHT, GARAGE DOOR, OIL DRAIN PAN, PARTS TRAY, PEGBOARD, SHELVING, SHOP LIGHT, SHOP TOWELS, SPILL KIT, TOOL CHEST, TOOL ROLL, WORKBENCH
- **38. Climate Control** (`systems-06`): AIR CONDITIONING, BLOWER MOTOR, CLIMATE CONTROL, COMPRESSOR, CONDENSER, DEFROSTER, EVAPORATOR, EXPANSION VALVE, RADIATOR, RECEIVER DRIER, RECIRCULATION, REFRIGERANT, VENTILATION
- **39. The Exhaust System** (`systems-07`): BACKPRESSURE, CATALYST, DOWNPIPE, EMISSIONS, EXHAUST MANIFOLD, FLEX PIPE, HEADERS, HEAT SHIELD, MUFFLER, OXYGEN SENSOR, RESONATOR, RUBBER HANGER, TAILPIPE
- **40. Highway Travel** (`driving-05`): CARPOOL, COMMUTE, CRUISE CONTROL, INTERSTATE, MILE MARKER, OFF RAMP, ON RAMP, OVERPASS, PASSING LANE, REST STOP, RUSH HOUR, TOLL BOOTH, TRAFFIC JAM
- **41. Inside the Block** (`engines-07`): BEARING CAP, BORE, CONNECTING ROD, COUNTERWEIGHT, CRANKCASE, CRANK PULLEY, CYLINDER LINER, DIPSTICK, ENGINE BLOCK, FREEZE PLUG, MAIN BEARING, OIL PAN, OIL PUMP, PISTON RING, STROKE, WRIST PIN
- **42. Body and Paint Care** (`maintenance-08`): BUFFER, CERAMIC COATING, CHAMOIS, CLAY BAR, CLEAR COAT, COMPOUND, DENT REPAIR, DETAILING, HAND WASH, MICROFIBER, PAINT CHIP, POLISH, RUST PROOFING, SEALANT, TOUCH UP PAINT, UNDERCOATING
- **43. Specialty Tools** (`tools-07`): BEARING PULLER, BORESCOPE, BRAKE BLEEDER, FLARING TOOL, OIL FILTER WRENCH, PICKLE FORK, RIVET GUN, SMOKE MACHINE, SOLDERING IRON, STETHOSCOPE, STUD EXTRACTOR, TAP AND DIE, THREAD CHASER, TUBE BENDER, TUBE CUTTER, VACUUM GAUGE
- **44. Driver Assistance** (`systems-08`): ADAPTIVE CRUISE, AIRBAG, AUTO HIGH BEAM, BACKUP CAMERA, BLIND SPOT, COLLISION ALERT, CRUMPLE ZONE, DRIVER MONITOR, HEAD UP DISPLAY, HILL START ASSIST, LANE KEEPING, NIGHT VISION, PARKING SENSOR, RAIN SENSOR, SURROUND VIEW, TRACTION CONTROL
- **45. Racing Disciplines** (`motorsport-06`): AUTOCROSS, DRAG RACE, DRIFTING, ENDURANCE, FORMULA, GYMKHANA, HILL CLIMB, ICE RACING, KARTING, OFF ROAD, OVAL RACING, RALLYCROSS, ROAD RACING, SPRINT, TIME ATTACK, TRACK DAY
- **46. From Workshop to Factory** (`history-05`): BLACKSMITH, CARRIAGE, CLAY MODEL, CONVEYOR, DEALERSHIP, DESIGN STUDIO, FOUNDRY, INTERCHANGEABLE, LABOR UNION, MACHINIST, SHOWROOM, STAMPING PRESS, TEST TRACK, TOOL AND DIE, WHEELWRIGHT, WORKSHOP
- **47. Learning to Drive** (`driving-06`): BLIND CORNER, CHECK MIRRORS, DRIVING TEST, HAND SIGNALS, HILL START, INSTRUCTOR, LANE CHANGE, LEARNER PERMIT, LICENSE, MERGING, PARALLEL PARKING, REVERSING, ROAD RULES, ROAD TEST, SPEED ZONE, THREE POINT TURN
- **48. Specs and Layouts** (`engines-08`): BOXER, CUBIC INCHES, DISPLACEMENT, FLAT FOUR, HORSEPOWER, INLINE, LITERS, LONGITUDINAL, MID ENGINE, POWER BAND, REDLINE, ROTARY ENGINE, STRAIGHT SIX, TORQUE, TRANSVERSE, TWIN CAM
- **49. Electrical Repairs** (`maintenance-09`): BATTERY CHARGER, BATTERY TERMINAL, BLOWN FUSE, CONTINUITY, CRIMP, FUSE BOX, GROUND STRAP, HEAT SHRINK, JUMPER CABLES, JUMP START, PARASITIC DRAW, SHORT CIRCUIT, SOLDER, TEST LIGHT, VOLTAGE, WIRING
- **50. Nuts, Bolts and Fasteners** (`tools-08`): ANTI SEIZE, CAP SCREW, CASTLE NUT, CIRCLIP, COTTER PIN, DOWEL PIN, FINE THREAD, FLANGE BOLT, FLAT WASHER, LOCK WASHER, ROLL PIN, SNAP RING, THREAD LOCKER, THREAD PITCH, TORQUE SPEC, WING NUT
- **51. Vehicle Electronics** (`systems-09`): ANTENNA, CENTRAL LOCKING, CONTROL MODULE, DATA BUS, DIAGNOSTIC PORT, FIRMWARE, GAUGE CLUSTER, IMMOBILIZER, INFOTAINMENT, KEY FOB, POWER LOCKS, REMOTE START, SOFTWARE UPDATE, SPEED SENSOR, TOUCHSCREEN, WIRING DIAGRAM
- **52. Aerodynamics and Setup** (`motorsport-07`): AIRFLOW, ANTI ROLL BAR, BALLAST, CANARD, DIFFUSER, DOWNFORCE, DRAG COEFFICIENT, FRONT SPLITTER, GROUND EFFECT, OVERSTEER, REAR WING, SLICKS, TIRE WARMERS, UNDERSTEER, VORTEX, WIND TUNNEL
- **53. Vintage Technology** (`history-06`): AM RADIO, BIAS PLY, CHOKE, DISTRIBUTOR CAP, EIGHT TRACK, FOUR SPEED, HAND THROTTLE, INNER TUBE, MAGNETO, RUMBLE SEAT, SIX VOLT, SPARK LEVER, THREE ON THE TREE, VACUUM ADVANCE, VENT WINDOW, WOODEN SPOKES
- **54. Road Trip Essentials** (`driving-07`): CAMPGROUND, COOLER, EMERGENCY KIT, GAS STATION, ITINERARY, LUGGAGE, NAVIGATION, PLAYLIST, POSTCARD, ROAD MAP, ROADSIDE, ROOF RACK, SCENIC ROUTE, SNACKS, SUNGLASSES, TRUNK
- **55. Electric Powertrains** (`engines-09`): BATTERY PACK, CONTACTOR, FAST CHARGING, HIGH VOLTAGE, INVERTER, KILOWATT HOUR, LITHIUM ION, ONBOARD CHARGER, ONE PEDAL, RANGE, REGENERATION, ROTOR, SINGLE SPEED, STATOR, THERMAL, TRACTION MOTOR
- **56. Suspension and Steering Repair** (`maintenance-10`): BALL JOINT, BUSHING, CAMBER, CASTER, CONTROL ARM, GREASE FITTING, IDLER ARM, PITMAN ARM, STEERING RACK, STRUT MOUNT, SWAY BAR LINK, THRUST ANGLE, TIE ROD END, TOE IN, WHEEL ALIGNMENT, WHEEL BEARING
- **57. Wheels, Tires and Chassis** (`systems-10`): ALLOY WHEEL, CHASSIS, CROSSMEMBER, FRAME RAIL, GROUND CLEARANCE, HUBCAP, LOAD RATING, RADIAL TIRE, RUN FLAT, SPEED RATING, SUBFRAME, TIRE BEAD, TRACK WIDTH, UNIBODY, WHEELBASE, WHEEL HUB
- **58. Life in the Paddock** (`motorsport-08`): CHAMPIONSHIP, CONSTRUCTOR, DATA LOGGER, DEBRIEF, LIVERY, MECHANIC, PODIUM, QUALIFYING, RACE ENGINEER, RACE SUIT, ROOKIE, SPONSOR, TEAM PRINCIPAL, TELEMETRY, TEST DRIVER, TROPHY
- **59. Weather and Road Skills** (`driving-08`): BLACK ICE, COUNTERSTEER, CROSSWIND, ENGINE BRAKING, FOG LIGHTS, FOUR WHEEL DRIVE, GLARE, GRAVEL, HYDROPLANING, NIGHT DRIVING, SNOW TIRES, TIRE CHAINS, TOWING, TRAILER, VISIBILITY, WINDING ROAD
- **60. Timing and Ignition** (`engines-10`): COIL PACK, CRANK SENSOR, DETONATION, DWELL, FIRING ORDER, FOUR STROKE, IGNITION TIMING, INTAKE STROKE, KNOCK SENSOR, PLUG WIRES, POWER STROKE, PREIGNITION, SPARK ADVANCE, TIMING LIGHT, TIMING MARK, TOP DEAD CENTER
