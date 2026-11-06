# Supported types within Endurain

## Supported activity types
The table below details the activity types supported by Endurain. `activity_type` in a response, an activity edit and the `type` filter of the activity lists is the key, a string; the API refuses the number.

| Name | Key |
| ---- | --- |
| Run | `run` |
| Trail run | `trail_run` |
| Track run | `track_run` |
| Treadmill run | `treadmill_run` |
| Virtual run | `virtual_run` |
| Road cycling | `ride` |
| Gravel cycling | `gravel_ride` |
| MTB cycling | `mtb_ride` |
| Commuting cycling | `commuting_ride` |
| Mixed surface cycling | `mixed_surface_ride` |
| Virtual cycling | `virtual_ride` |
| Indoor cycling | `indoor_ride` |
| E-Bike cycling | `ebike_ride` |
| E-Bike mountain cycling | `ebike_mountain_ride` |
| Indoor swimming | `lap_swimming` |
| Open water swimming | `open_water_swimming` |
| General workout | `workout` |
| Walk | `walk` |
| Indoor walk | `indoor_walk` |
| Hike | `hike` |
| Rowing | `rowing` |
| Yoga | `yoga` |
| Alpine ski | `alpine_ski` |
| Nordic Ski | `nordic_ski` |
| Snowboard | `snowboard` |
| Ice Skate | `ice_skate` |
| Transition | `transition` |
| Strength Training | `strength_training` |
| Crossfit | `crossfit` |
| Tennis | `tennis` |
| Table Tennis | `table_tennis` |
| Badminton | `badminton` |
| Squash | `squash` |
| Racquetball | `racquetball` |
| Pickleball | `pickleball` |
| Padel | `padel` |
| Windsurf | `windsurf` |
| Stand up paddling | `stand_up_paddling` |
| Surf | `surf` |
| Soccer | `soccer` |
| Cardio training | `cardio_training` |
| Kayaking | `kayaking` |
| Sailing | `sailing` |
| Snow shoeing | `snow_shoeing` |
| Inline skating | `inline_skating` |
| HIIT | `hiit` |
| Jump rope | `jump_rope` |


## Supported gear types
The table below details the gear types supported by Endurain. `gear_type` in a gear and the `gear_type` filter of the gear list is the name, a string; the API refuses the number.

| Name               | Notes                                   |
|--------------------|-----------------------------------------|
| bike               | N/A                                     |
| shoes              | N/A                                     |
| wetsuit            | N/A                                     |
| racquet            | N/A                                     |
| ski                | N/A                                     |
| snowboard          | N/A                                     |
| windsurf           | N/A                                     |
| water_sports_board | Example: stand up paddle and surf board |


## Supported bike component gear types
The table below details the bike gear component types supported by Endurain:

| Value                       |
|-----------------------------|
| back_break_oil              |
| back_break_pads             |
| back_break_rotor            |
| back_tire                   |
| back_tube                   |
| back_tubeless_sealant       |
| back_tubeless_rim_tape      |
| back_wheel                  |
| back_wheel_valve            |
| bottom_bracket              |
| bottle_cage                 |
| cassette                    |
| chain                       |
| computer_mount              |
| crank_left_power_meter      |
| crank_right_power_meter     |
| crankset                    |
| crankset_power_meter        |
| fork                        |
| frame                       |
| front_break_oil             |
| front_break_pads            |
| front_break_rotor           |
| front_derailleur            |
| front_shifter               |
| front_tire                  |
| front_tube                  |
| front_tubeless_sealant      |
| front_tubeless_rim_tape     |
| front_wheel                 |
| front_wheel_valve           |
| grips                       |
| handlebar                   |
| handlebar_tape              |
| headset                     |
| pedals                      |
| pedals_left_power_meter     |
| pedals_power_meter          |
| pedals_right_power_meter    |
| rear_derailleur             |
| rear_shifter                |
| saddle                      |
| seatpost                    |
| stem                        |


## Supported shoes component gear types
The table below details the shoes component gear types supported by Endurain:

| Value                       |
|-----------------------------|
| cleats                      |
| insoles                     |
| laces                       |


## Supported racquet component gear types
The table below details the racquet component gear types supported by Endurain:

| Value                       |
|-----------------------------|
| basegrip                    |
| bumpers                     |
| grommets                    |
| overgrip                    |
| strings                     |


## Supported windsurf component gear types
The table below details the windsurf component gear types supported by Endurain:

| Value                       |
|-----------------------------|
| sail                        |
| board                       |
| mast                        |
| boom                        |
| mast_extension              |
| mast_base                   |
| mast_universal_joint        |
| fin                         |
| footstraps                  |
| harness_lines               |
| rigging_lines               |
| footpad                     |
| impact_vest                 |
| lifeguard_vest              |
| helmet                      |
| wing                        |
| front_foil                  |
| stabilizer                  |
| fuselage                    |




## Other enumerated values

Every enumerated value is a string. The API refuses the number the database stores.

| Field | Values |
| ----- | ------ |
| `visibility` of an activity, the `visibility` of the bulk edit and `default_activity_visibility` of the profile | `public`, `followers`, `private` |
| `media_type` of an activity photo | `photo` |
| `type` of a notification | `new_activity`, `duplicate_activity`, `new_follower_request`, `new_follower_request_accepted`, `garmin_token_expired`, `strava_token_expired`, `strava_data_deleted`, `idp_linked`, `account_security_changed`, `new_device_sign_in`, `admin_new_sign_up_approval_request` |
| `bristol_type` of a bowel movement | `type_1` to `type_7` |
| `stage_type` of a sleep stage | `deep`, `light`, `rem`, `awake` |
| `stream_type` of an activity stream | `heart_rate`, `power`, `cadence`, `elevation`, `speed`, `pace`, `map`, `temperature` |

`is_strava_linked` and `is_garminconnect_linked` of the signed-in user are booleans.
