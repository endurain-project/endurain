export const GEAR_BIKE_COMPONENT_TYPES = [
	"back_break_oil",
	"back_break_pads",
	"back_break_rotor",
	"back_tire",
	"back_tube",
	"back_tubeless_rim_tape",
	"back_tubeless_sealant",
	"back_wheel",
	"back_wheel_valve",
	"bottom_bracket",
	"bottle_cage",
	"cassette",
	"chain",
	"computer_mount",
	"crank_left_power_meter",
	"crank_right_power_meter",
	"crankset",
	"crankset_power_meter",
	"fork",
	"frame",
	"front_break_oil",
	"front_break_pads",
	"front_break_rotor",
	"front_derailleur",
	"front_shifter",
	"front_tire",
	"front_tube",
	"front_tubeless_rim_tape",
	"front_tubeless_sealant",
	"front_wheel",
	"front_wheel_valve",
	"grips",
	"handlebar",
	"handlebar_tape",
	"headset",
	"pedals",
	"pedals_left_power_meter",
	"pedals_power_meter",
	"pedals_right_power_meter",
	"rear_derailleur",
	"rear_shifter",
	"saddle",
	"seatpost",
	"stem"
];

const bikeTypeLabelMap = {
	"back_break_oil": t => t("gearComponentListComponent.gearComponentBackBreakOil"),
	"back_break_pads": t => t("gearComponentListComponent.gearComponentBackBreakPads"),
	"back_break_rotor": t => t("gearComponentListComponent.gearComponentBackBreakRotor"),
	"back_tire": t => t("gearComponentListComponent.gearComponentBackTire"),
	"back_tube": t => t("gearComponentListComponent.gearComponentBackTube"),
	"back_tubeless_rim_tape": t => t("gearComponentListComponent.gearComponentBackTubelessRimTape"),
	"back_tubeless_sealant": t => t("gearComponentListComponent.gearComponentBackTubelessSealant"),
	"back_wheel": t => t("gearComponentListComponent.gearComponentBackWheel"),
	"back_wheel_valve": t => t("gearComponentListComponent.gearComponentBackWheelValve"),
	"bottom_bracket": t => t("gearComponentListComponent.gearComponentBottomBracket"),
	"bottle_cage": t => t("gearComponentListComponent.gearComponentBottleCage"),
	"cassette": t => t("gearComponentListComponent.gearComponentCassette"),
	"chain": t => t("gearComponentListComponent.gearComponentChain"),
	"computer_mount": t => t("gearComponentListComponent.gearComponentComputerMount"),
	"crank_left_power_meter": t => t("gearComponentListComponent.gearComponentCrankLeftPowerMeter"),
	"crank_right_power_meter": t => t("gearComponentListComponent.gearComponentCrankRightPowerMeter"),
	"crankset": t => t("gearComponentListComponent.gearComponentCrankset"),
	"crankset_power_meter": t => t("gearComponentListComponent.gearComponentCranksetPowerMeter"),
	"fork": t => t("gearComponentListComponent.gearComponentFork"),
	"frame": t => t("gearComponentListComponent.gearComponentFrame"),
	"front_break_oil": t => t("gearComponentListComponent.gearComponentFrontBreakOil"),
	"front_break_pads": t => t("gearComponentListComponent.gearComponentFrontBreakPads"),
	"front_break_rotor": t => t("gearComponentListComponent.gearComponentFrontBreakRotor"),
	"front_derailleur": t => t("gearComponentListComponent.gearComponentFrontDerailleur"),
	"front_shifter": t => t("gearComponentListComponent.gearComponentFrontShifter"),
	"front_tire": t => t("gearComponentListComponent.gearComponentFrontTire"),
	"front_tube": t => t("gearComponentListComponent.gearComponentFrontTube"),
	"front_tubeless_rim_tape": t => t("gearComponentListComponent.gearComponentFrontTubelessRimTape"),
	"front_tubeless_sealant": t => t("gearComponentListComponent.gearComponentFrontTubelessSealant"),
	"front_wheel": t => t("gearComponentListComponent.gearComponentFrontWheel"),
	"front_wheel_valve": t => t("gearComponentListComponent.gearComponentFrontWheelValve"),
	"grips": t => t("gearComponentListComponent.gearComponentGrips"),
	"handlebar": t => t("gearComponentListComponent.gearComponentHandlebar"),
	"handlebar_tape": t => t("gearComponentListComponent.gearComponentHandlebarTape"),
	"headset": t => t("gearComponentListComponent.gearComponentHeadset"),
	"pedals": t => t("gearComponentListComponent.gearComponentPedals"),
	"pedals_left_power_meter": t => t("gearComponentListComponent.gearComponentPedalsLeftPowerMeter"),
	"pedals_power_meter": t => t("gearComponentListComponent.gearComponentPedalsPowerMeter"),
	"pedals_right_power_meter": t => t("gearComponentListComponent.gearComponentPedalsRightPowerMeter"),
	"rear_derailleur": t => t("gearComponentListComponent.gearComponentRearDerailleur"),
	"rear_shifter": t => t("gearComponentListComponent.gearComponentRearShifter"),
	"saddle": t => t("gearComponentListComponent.gearComponentSaddle"),
	"seatpost": t => t("gearComponentListComponent.gearComponentSeatpost"),
	"stem": t => t("gearComponentListComponent.gearComponentStem"),
};

const bikeTypeAvatarMap = {
	"back_break_oil": "/src/assets/avatar/gearComponents/backBreakOil1.png",
	"back_break_pads": "/src/assets/avatar/gearComponents/backBreakPads1.png",
	"back_break_rotor": "/src/assets/avatar/gearComponents/diskBreakRotor1.png",
	"back_tire": "/src/assets/avatar/gearComponents/tire1.png",
	"back_tube": "/src/assets/avatar/gearComponents/tube1.png",
	"back_tubeless_rim_tape": "/src/assets/avatar/gearComponents/tubelessRimTape1.png",
	"back_tubeless_sealant": "/src/assets/avatar/gearComponents/tubelessSealant1.png",
	"back_wheel": "/src/assets/avatar/gearComponents/wheel1.png",
	"back_wheel_valve": "/src/assets/avatar/gearComponents/wheelValve1.png",
	"bottom_bracket": "/src/assets/avatar/gearComponents/bottomBracket1.png",
	"bottle_cage": "/src/assets/avatar/gearComponents/bottleCage1.png",
	"cassette": "/src/assets/avatar/gearComponents/cassette1.png",
	"chain": "/src/assets/avatar/gearComponents/chain1.png",
	"computer_mount": "/src/assets/avatar/gearComponents/computerMount1.png",
	"crank_left_power_meter": "/src/assets/avatar/gearComponents/crankPowerMeter1.png",
	"crank_right_power_meter": "/src/assets/avatar/gearComponents/crankPowerMeter1.png",
	"crankset": "/src/assets/avatar/gearComponents/crankset1.png",
	"crankset_power_meter": "/src/assets/avatar/gearComponents/crankPowerMeter1.png",
	"fork": "/src/assets/avatar/gearComponents/fork1.png",
	"frame": "/src/assets/avatar/gearComponents/frame1.png",
	"front_break_oil": "/src/assets/avatar/gearComponents/backBreakOil1.png",
	"front_break_pads": "/src/assets/avatar/gearComponents/backBreakPads1.png",
	"front_break_rotor": "/src/assets/avatar/gearComponents/diskBreakRotor1.png",
	"front_derailleur": "/src/assets/avatar/gearComponents/frontDerailleur1.png",
	"front_shifter": "/src/assets/avatar/gearComponents/shifter1.png",
	"front_tire": "/src/assets/avatar/gearComponents/tire1.png",
	"front_tube": "/src/assets/avatar/gearComponents/tube1.png",
	"front_tubeless_rim_tape": "/src/assets/avatar/gearComponents/tubelessRimTape1.png",
	"front_tubeless_sealant": "/src/assets/avatar/gearComponents/tubelessSealant1.png",
	"front_wheel": "/src/assets/avatar/gearComponents/wheel1.png",
	"front_wheel_valve": "/src/assets/avatar/gearComponents/wheelValve1.png",
	"grips": "/src/assets/avatar/gearComponents/grips1.png",
	"handlebar": "/src/assets/avatar/gearComponents/handlebar1.png",
	"handlebar_tape": "/src/assets/avatar/gearComponents/handlebarTape1.png",
	"headset": "/src/assets/avatar/gearComponents/headset1.png",
	"pedals": "/src/assets/avatar/gearComponents/pedals1.png",
	"pedals_left_power_meter": "/src/assets/avatar/gearComponents/pedalPowerMeter1.png",
	"pedals_power_meter": "/src/assets/avatar/gearComponents/pedalPowerMeter1.png",
	"pedals_right_power_meter": "/src/assets/avatar/gearComponents/pedalPowerMeter1.png",
	"rear_derailleur": "/src/assets/avatar/gearComponents/rearDerailleur1.png",
	"rear_shifter": "/src/assets/avatar/gearComponents/shifter1.png",
	"saddle": "/src/assets/avatar/gearComponents/saddle1.png",
	"seatpost": "/src/assets/avatar/gearComponents/seatpost1.png",
	"stem": "/src/assets/avatar/gearComponents/stem1.png",
};

export const GEAR_SHOES_COMPONENT_TYPES = [
    "cleats",
    "insoles",
    "laces",
]

const shoesTypeLabelMap = {
	"cleats": t => t("gearComponentListComponent.gearComponentCleats"),
	"insoles": t => t("gearComponentListComponent.gearComponentInsoles"),
	"laces": t => t("gearComponentListComponent.gearComponentLaces"),
};

const shoesTypeAvatarMap = {
	"cleats": "/src/assets/avatar/gearComponents/cleats1.png",
	"insoles": "/src/assets/avatar/gearComponents/insoles1.png",
	"laces": "/src/assets/avatar/gearComponents/laces1.png",
};


export const GEAR_RACQUET_COMPONENT_TYPES = [
    "basegrip",
    "bumpers",
    "grommets",
    "overgrip",
    "strings",
]

const racquetTypeLabelMap = {
	"basegrip": t => t("gearComponentListComponent.gearComponentBaseGrip"),
	"bumpers": t => t("gearComponentListComponent.gearComponentBumpers"),
	"grommets": t => t("gearComponentListComponent.gearComponentGrommets"),
	"overgrip": t => t("gearComponentListComponent.gearComponentOverGrip"),
	"strings": t => t("gearComponentListComponent.gearComponentStrings"),
};

const racquetTypeAvatarMap = {
	"basegrip": "/src/assets/avatar/gearComponents/tubelessRimTape1.png",
	"bumpers": "/src/assets/avatar/gearComponents/bumpers1.png",
	"grommets": "/src/assets/avatar/gearComponents/grommets1.png",
	"overgrip": "/src/assets/avatar/gearComponents/handlebarTape1.png",
	"strings": "/src/assets/avatar/gearComponents/strings1.png",
};

export const GEAR_WINDSURF_COMPONENT_TYPES = [
    "sail",
    "board",
    "mast",
    "boom",
    "mast_extension",
    "mast_base",
    "mast_universal_joint",
    "fin",
    "footstraps",
    "harness_lines",
    "rigging_lines",
    "footpad",
    "impact_vest",
    "lifeguard_vest",
    "helmet",
]

const windsurfTypeLabelMap = {
	"sail": t => t("gearComponentListComponent.gearComponentSail"),
	"board": t => t("gearComponentListComponent.gearComponentBoard"),
	"mast": t => t("gearComponentListComponent.gearComponentMast"),
	"boom": t => t("gearComponentListComponent.gearComponentBoom"),
	"mast_extension": t => t("gearComponentListComponent.gearComponentMastExtension"),
	"mast_base": t => t("gearComponentListComponent.gearComponentMastBase"),
	"mast_universal_joint": t => t("gearComponentListComponent.gearComponentMastUniversalJoint"),
	"fin": t => t("gearComponentListComponent.gearComponentFin"),
	"footstraps": t => t("gearComponentListComponent.gearComponentFootstraps"),
	"harness_lines": t => t("gearComponentListComponent.gearComponentHarnessLines"),
	"rigging_lines": t => t("gearComponentListComponent.gearComponentRiggingLines"),
	"footpad": t => t("gearComponentListComponent.gearComponentFootpad"),
	"impact_vest": t => t("gearComponentListComponent.gearComponentImpactVest"),
	"impact_vest": t => t("gearComponentListComponent.gearComponentLifeguardVest"),
	"helmet": t => t("gearComponentListComponent.gearComponentHelmet"),
};

const windsurfTypeAvatarMap = {
	"sail": "/src/assets/avatar/gearComponents/windsurfSail1.png",
	"board": "/src/assets/avatar/gearComponents/windsurfBoard1.png",
	"mast": "/src/assets/avatar/gearComponents/windsurfMast1.png",
	"boom": "/src/assets/avatar/gearComponents/windsurfBoom1.png",
	"mast_extension": "/src/assets/avatar/gearComponents/windsurfMastExtension1.png",
	"mast_base": "/src/assets/avatar/gearComponents/windsurfMastBase1.png",
	"mast_universal_joint": "/src/assets/avatar/gearComponents/windsurfMastUniversalJoint1.png",
	"fin": "/src/assets/avatar/gearComponents/fin1.png",
	"footstraps": "/src/assets/avatar/gearComponents/footstrap1.png",
	"harness_lines": "/src/assets/avatar/gearComponents/harnessLines1.png",
	"rigging_lines": "/src/assets/avatar/gearComponents/riggingLines1.png",
	"footpad": "/src/assets/avatar/gearComponents/footpad1.png",
	"impact_vest": "/src/assets/avatar/gearComponents/impactVest1.png",
	"impact_vest": "/src/assets/avatar/gearComponents/lifeguardVest1.png",
	"helmet": "/src/assets/avatar/gearComponents/helmet1.png",
};

export function getGearBikeComponentType(type, t) {
	if (GEAR_BIKE_COMPONENT_TYPES.includes(type)) {
		return bikeTypeLabelMap[type] ? bikeTypeLabelMap[type](t) : type;
	}
	return type;
}

export function getGearBikeComponentAvatar(type) {
	if (GEAR_BIKE_COMPONENT_TYPES.includes(type)) {
		return bikeTypeAvatarMap[type] || "";
	}
	return "";
}

export function getGearShoesComponentType(type, t) {
	if (GEAR_SHOES_COMPONENT_TYPES.includes(type)) {
		return shoesTypeLabelMap[type] ? shoesTypeLabelMap[type](t) : type;
	}
	return type;
}

export function getGearShoesComponentAvatar(type) {
	if (GEAR_SHOES_COMPONENT_TYPES.includes(type)) {
		return shoesTypeAvatarMap[type] || "";
	}
	return "";
}

export function getGearRacquetComponentType(type, t) {
	if (GEAR_RACQUET_COMPONENT_TYPES.includes(type)) {
		return racquetTypeLabelMap[type] ? racquetTypeLabelMap[type](t) : type;
	}
	return type;
}

export function getGearRacquetComponentAvatar(type) {
	if (GEAR_RACQUET_COMPONENT_TYPES.includes(type)) {
		return racquetTypeAvatarMap[type] || "";
	}
	return "";
}

export function getGearWindsurfComponentType(type, t) {
	if (GEAR_WINDSURF_COMPONENT_TYPES.includes(type)) {
		return windsurfTypeLabelMap[type] ? windsurfTypeLabelMap[type](t) : type;
	}
	return type;
}

export function getGearWindsurfComponentAvatar(type) {
	if (GEAR_WINDSURF_COMPONENT_TYPES.includes(type)) {
		return windsurfTypeAvatarMap[type] || "";
	}
	return "";
}