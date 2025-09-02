// Import all component images
// Bike component images
import diskBreakOil1 from '@/assets/avatar/gearComponents/diskBreakOil1.png'
import diskBreakPads1 from '@/assets/avatar/gearComponents/diskBreakPads1.png'
import diskBreakRotor1 from '@/assets/avatar/gearComponents/diskBreakRotor1.png'
import tire1 from '@/assets/avatar/gearComponents/tire1.png'
import tube1 from '@/assets/avatar/gearComponents/tube1.png'
import tubelessRimTape1 from '@/assets/avatar/gearComponents/tubelessRimTape1.png'
import tubelessSealant1 from '@/assets/avatar/gearComponents/tubelessSealant1.png'
import wheel1 from '@/assets/avatar/gearComponents/wheel1.png'
import wheelValve1 from '@/assets/avatar/gearComponents/wheelValve1.png'
import bottomBracket1 from '@/assets/avatar/gearComponents/bottomBracket1.png'
import bottleCage1 from '@/assets/avatar/gearComponents/bottleCage1.png'
import cassette1 from '@/assets/avatar/gearComponents/cassette1.png'
import chain1 from '@/assets/avatar/gearComponents/chain1.png'
import computerMount1 from '@/assets/avatar/gearComponents/computerMount1.png'
import crankPowerMeter1 from '@/assets/avatar/gearComponents/crankPowerMeter1.png'
import crankset1 from '@/assets/avatar/gearComponents/crankset1.png'
import fork1 from '@/assets/avatar/gearComponents/fork1.png'
import frame1 from '@/assets/avatar/gearComponents/frame1.png'
import frontDerailleur1 from '@/assets/avatar/gearComponents/frontDerailleur1.png'
import shifter1 from '@/assets/avatar/gearComponents/shifter1.png'
import grips1 from '@/assets/avatar/gearComponents/grips1.png'
import handlebar1 from '@/assets/avatar/gearComponents/handlebar1.png'
import handlebarTape1 from '@/assets/avatar/gearComponents/handlebarTape1.png'
import headset1 from '@/assets/avatar/gearComponents/headset1.png'
import pedals1 from '@/assets/avatar/gearComponents/pedals1.png'
import pedalPowerMeter1 from '@/assets/avatar/gearComponents/pedalPowerMeter1.png'
import rearDerailleur1 from '@/assets/avatar/gearComponents/rearDerailleur1.png'
import saddle1 from '@/assets/avatar/gearComponents/saddle1.png'
import seatpost1 from '@/assets/avatar/gearComponents/seatpost1.png'
import stem1 from '@/assets/avatar/gearComponents/stem1.png'

// Shoes component images
import cleats1 from '@/assets/avatar/gearComponents/cleats1.png'
import insoles1 from '@/assets/avatar/gearComponents/insoles1.png'
import laces1 from '@/assets/avatar/gearComponents/laces1.png'

// Racquet component images
import bumpers1 from '@/assets/avatar/gearComponents/bumpers1.png'
import grommets1 from '@/assets/avatar/gearComponents/grommets1.png'
import strings1 from '@/assets/avatar/gearComponents/strings1.png'

// Windsurf component images
import windsurfSail1 from '@/assets/avatar/gearComponents/windsurfSail1.png'
import windsurfBoard1 from '@/assets/avatar/gearComponents/windsurfBoard1.png'
import windsurfMast1 from '@/assets/avatar/gearComponents/windsurfMast1.png'
import windsurfBoom1 from '@/assets/avatar/gearComponents/windsurfBoom1.png'
import windsurfMastExtension1 from '@/assets/avatar/gearComponents/windsurfMastExtension1.png'
import windsurfMastBase1 from '@/assets/avatar/gearComponents/windsurfMastBase1.png'
import windsurfMastUniversalJoint1 from '@/assets/avatar/gearComponents/windsurfMastUniversalJoint1.png'
import fin1 from '@/assets/avatar/gearComponents/fin1.png'
import footstrap1 from '@/assets/avatar/gearComponents/footstrap1.png'
import harnessLines1 from '@/assets/avatar/gearComponents/harnessLines1.png'
import riggingLines1 from '@/assets/avatar/gearComponents/riggingLines1.png'
import footpad1 from '@/assets/avatar/gearComponents/footpad1.png'
import impactVest1 from '@/assets/avatar/gearComponents/impactVest1.png'
import lifeguardVest1 from '@/assets/avatar/gearComponents/lifeguardVest1.png'
import helmet1 from '@/assets/avatar/gearComponents/helmet1.png'
import wing1 from '@/assets/avatar/gearComponents/wing1.png'
import frontFoil1 from '@/assets/avatar/gearComponents/frontFoil1.png'
import stabilizer1 from '@/assets/avatar/gearComponents/stabilizer1.png'
import fuselage1 from '@/assets/avatar/gearComponents/fuselage1.png'

export const GEAR_BIKE_COMPONENT_TYPES = [
  'back_break_oil',
  'back_break_pads',
  'back_break_rotor',
  'back_tire',
  'back_tube',
  'back_tubeless_rim_tape',
  'back_tubeless_sealant',
  'back_wheel',
  'back_wheel_valve',
  'bottom_bracket',
  'bottle_cage',
  'cassette',
  'chain',
  'computer_mount',
  'crank_left_power_meter',
  'crank_right_power_meter',
  'crankset',
  'crankset_power_meter',
  'fork',
  'frame',
  'front_break_oil',
  'front_break_pads',
  'front_break_rotor',
  'front_derailleur',
  'front_shifter',
  'front_tire',
  'front_tube',
  'front_tubeless_rim_tape',
  'front_tubeless_sealant',
  'front_wheel',
  'front_wheel_valve',
  'grips',
  'handlebar',
  'handlebar_tape',
  'headset',
  'pedals',
  'pedals_left_power_meter',
  'pedals_power_meter',
  'pedals_right_power_meter',
  'rear_derailleur',
  'rear_shifter',
  'saddle',
  'seatpost',
  'stem'
]

const bikeTypeLabelMap = {
  back_break_oil: (t) => t('gearComponentListComponent.gearComponentBackBreakOil'),
  back_break_pads: (t) => t('gearComponentListComponent.gearComponentBackBreakPads'),
  back_break_rotor: (t) => t('gearComponentListComponent.gearComponentBackBreakRotor'),
  back_tire: (t) => t('gearComponentListComponent.gearComponentBackTire'),
  back_tube: (t) => t('gearComponentListComponent.gearComponentBackTube'),
  back_tubeless_rim_tape: (t) => t('gearComponentListComponent.gearComponentBackTubelessRimTape'),
  back_tubeless_sealant: (t) => t('gearComponentListComponent.gearComponentBackTubelessSealant'),
  back_wheel: (t) => t('gearComponentListComponent.gearComponentBackWheel'),
  back_wheel_valve: (t) => t('gearComponentListComponent.gearComponentBackWheelValve'),
  bottom_bracket: (t) => t('gearComponentListComponent.gearComponentBottomBracket'),
  bottle_cage: (t) => t('gearComponentListComponent.gearComponentBottleCage'),
  cassette: (t) => t('gearComponentListComponent.gearComponentCassette'),
  chain: (t) => t('gearComponentListComponent.gearComponentChain'),
  computer_mount: (t) => t('gearComponentListComponent.gearComponentComputerMount'),
  crank_left_power_meter: (t) => t('gearComponentListComponent.gearComponentCrankLeftPowerMeter'),
  crank_right_power_meter: (t) => t('gearComponentListComponent.gearComponentCrankRightPowerMeter'),
  crankset: (t) => t('gearComponentListComponent.gearComponentCrankset'),
  crankset_power_meter: (t) => t('gearComponentListComponent.gearComponentCranksetPowerMeter'),
  fork: (t) => t('gearComponentListComponent.gearComponentFork'),
  frame: (t) => t('gearComponentListComponent.gearComponentFrame'),
  front_break_oil: (t) => t('gearComponentListComponent.gearComponentFrontBreakOil'),
  front_break_pads: (t) => t('gearComponentListComponent.gearComponentFrontBreakPads'),
  front_break_rotor: (t) => t('gearComponentListComponent.gearComponentFrontBreakRotor'),
  front_derailleur: (t) => t('gearComponentListComponent.gearComponentFrontDerailleur'),
  front_shifter: (t) => t('gearComponentListComponent.gearComponentFrontShifter'),
  front_tire: (t) => t('gearComponentListComponent.gearComponentFrontTire'),
  front_tube: (t) => t('gearComponentListComponent.gearComponentFrontTube'),
  front_tubeless_rim_tape: (t) => t('gearComponentListComponent.gearComponentFrontTubelessRimTape'),
  front_tubeless_sealant: (t) => t('gearComponentListComponent.gearComponentFrontTubelessSealant'),
  front_wheel: (t) => t('gearComponentListComponent.gearComponentFrontWheel'),
  front_wheel_valve: (t) => t('gearComponentListComponent.gearComponentFrontWheelValve'),
  grips: (t) => t('gearComponentListComponent.gearComponentGrips'),
  handlebar: (t) => t('gearComponentListComponent.gearComponentHandlebar'),
  handlebar_tape: (t) => t('gearComponentListComponent.gearComponentHandlebarTape'),
  headset: (t) => t('gearComponentListComponent.gearComponentHeadset'),
  pedals: (t) => t('gearComponentListComponent.gearComponentPedals'),
  pedals_left_power_meter: (t) => t('gearComponentListComponent.gearComponentPedalsLeftPowerMeter'),
  pedals_power_meter: (t) => t('gearComponentListComponent.gearComponentPedalsPowerMeter'),
  pedals_right_power_meter: (t) =>
    t('gearComponentListComponent.gearComponentPedalsRightPowerMeter'),
  rear_derailleur: (t) => t('gearComponentListComponent.gearComponentRearDerailleur'),
  rear_shifter: (t) => t('gearComponentListComponent.gearComponentRearShifter'),
  saddle: (t) => t('gearComponentListComponent.gearComponentSaddle'),
  seatpost: (t) => t('gearComponentListComponent.gearComponentSeatpost'),
  stem: (t) => t('gearComponentListComponent.gearComponentStem')
}

const bikeTypeAvatarMap = {
  back_break_oil: diskBreakOil1,
  back_break_pads: diskBreakPads1,
  back_break_rotor: diskBreakRotor1,
  back_tire: tire1,
  back_tube: tube1,
  back_tubeless_rim_tape: tubelessRimTape1,
  back_tubeless_sealant: tubelessSealant1,
  back_wheel: wheel1,
  back_wheel_valve: wheelValve1,
  bottom_bracket: bottomBracket1,
  bottle_cage: bottleCage1,
  cassette: cassette1,
  chain: chain1,
  computer_mount: computerMount1,
  crank_left_power_meter: crankPowerMeter1,
  crank_right_power_meter: crankPowerMeter1,
  crankset: crankset1,
  crankset_power_meter: crankPowerMeter1,
  fork: fork1,
  frame: frame1,
  front_break_oil: diskBreakOil1,
  front_break_pads: diskBreakPads1,
  front_break_rotor: diskBreakRotor1,
  front_derailleur: frontDerailleur1,
  front_shifter: shifter1,
  front_tire: tire1,
  front_tube: tube1,
  front_tubeless_rim_tape: tubelessRimTape1,
  front_tubeless_sealant: tubelessSealant1,
  front_wheel: wheel1,
  front_wheel_valve: wheelValve1,
  grips: grips1,
  handlebar: handlebar1,
  handlebar_tape: handlebarTape1,
  headset: headset1,
  pedals: pedals1,
  pedals_left_power_meter: pedalPowerMeter1,
  pedals_power_meter: pedalPowerMeter1,
  pedals_right_power_meter: pedalPowerMeter1,
  rear_derailleur: rearDerailleur1,
  rear_shifter: shifter1,
  saddle: saddle1,
  seatpost: seatpost1,
  stem: stem1
}

export const GEAR_SHOES_COMPONENT_TYPES = ['cleats', 'insoles', 'laces']

const shoesTypeLabelMap = {
  cleats: (t) => t('gearComponentListComponent.gearComponentCleats'),
  insoles: (t) => t('gearComponentListComponent.gearComponentInsoles'),
  laces: (t) => t('gearComponentListComponent.gearComponentLaces')
}

const shoesTypeAvatarMap = {
  cleats: cleats1,
  insoles: insoles1,
  laces: laces1
}

export const GEAR_RACQUET_COMPONENT_TYPES = [
  'basegrip',
  'bumpers',
  'grommets',
  'overgrip',
  'strings'
]

const racquetTypeLabelMap = {
  basegrip: (t) => t('gearComponentListComponent.gearComponentBaseGrip'),
  bumpers: (t) => t('gearComponentListComponent.gearComponentBumpers'),
  grommets: (t) => t('gearComponentListComponent.gearComponentGrommets'),
  overgrip: (t) => t('gearComponentListComponent.gearComponentOverGrip'),
  strings: (t) => t('gearComponentListComponent.gearComponentStrings')
}

const racquetTypeAvatarMap = {
  basegrip: tubelessRimTape1, // Reusing tubelessRimTape1
  bumpers: bumpers1,
  grommets: grommets1,
  overgrip: handlebarTape1, // Reusing handlebarTape1
  strings: strings1
}

export const GEAR_WINDSURF_COMPONENT_TYPES = [
  'sail',
  'board',
  'mast',
  'boom',
  'mast_extension',
  'mast_base',
  'mast_universal_joint',
  'fin',
  'footstraps',
  'harness_lines',
  'rigging_lines',
  'footpad',
  'impact_vest',
  'lifeguard_vest',
  'helmet',
  'wing',
  'front_foil',
  'stabilizer',
  'fuselage'
]

const windsurfTypeLabelMap = {
  sail: (t) => t('gearComponentListComponent.gearComponentSail'),
  board: (t) => t('gearComponentListComponent.gearComponentBoard'),
  mast: (t) => t('gearComponentListComponent.gearComponentMast'),
  boom: (t) => t('gearComponentListComponent.gearComponentBoom'),
  mast_extension: (t) => t('gearComponentListComponent.gearComponentMastExtension'),
  mast_base: (t) => t('gearComponentListComponent.gearComponentMastBase'),
  mast_universal_joint: (t) => t('gearComponentListComponent.gearComponentMastUniversalJoint'),
  fin: (t) => t('gearComponentListComponent.gearComponentFin'),
  footstraps: (t) => t('gearComponentListComponent.gearComponentFootstraps'),
  harness_lines: (t) => t('gearComponentListComponent.gearComponentHarnessLines'),
  rigging_lines: (t) => t('gearComponentListComponent.gearComponentRiggingLines'),
  footpad: (t) => t('gearComponentListComponent.gearComponentFootpad'),
  impact_vest: (t) => t('gearComponentListComponent.gearComponentImpactVest'),
  lifeguard_vest: (t) => t('gearComponentListComponent.gearComponentLifeguardVest'),
  helmet: (t) => t('gearComponentListComponent.gearComponentHelmet'),
  wing: (t) => t('gearComponentListComponent.gearComponentWing'),
  front_foil: (t) => t('gearComponentListComponent.gearComponentFrontFoil'),
  stabilizer: (t) => t('gearComponentListComponent.gearComponentStabilizer'),
  fuselage: (t) => t('gearComponentListComponent.gearComponentFuselage')
}

const windsurfTypeAvatarMap = {
  sail: windsurfSail1,
  board: windsurfBoard1,
  mast: windsurfMast1,
  boom: windsurfBoom1,
  mast_extension: windsurfMastExtension1,
  mast_base: windsurfMastBase1,
  mast_universal_joint: windsurfMastUniversalJoint1,
  fin: fin1,
  footstraps: footstrap1,
  harness_lines: harnessLines1,
  rigging_lines: riggingLines1,
  footpad: footpad1,
  impact_vest: impactVest1,
  lifeguard_vest: lifeguardVest1,
  helmet: helmet1,
  wing: wing1,
  front_foil: frontFoil1,
  stabilizer: stabilizer1,
  fuselage: fuselage1
}

export function getGearBikeComponentType(type, t) {
  if (GEAR_BIKE_COMPONENT_TYPES.includes(type)) {
    return bikeTypeLabelMap[type] ? bikeTypeLabelMap[type](t) : type
  }
  return type
}

export function getGearBikeComponentAvatar(type) {
  if (GEAR_BIKE_COMPONENT_TYPES.includes(type)) {
    return bikeTypeAvatarMap[type] || ''
  }
  return ''
}

export function getGearShoesComponentType(type, t) {
  if (GEAR_SHOES_COMPONENT_TYPES.includes(type)) {
    return shoesTypeLabelMap[type] ? shoesTypeLabelMap[type](t) : type
  }
  return type
}

export function getGearShoesComponentAvatar(type) {
  if (GEAR_SHOES_COMPONENT_TYPES.includes(type)) {
    return shoesTypeAvatarMap[type] || ''
  }
  return ''
}

export function getGearRacquetComponentType(type, t) {
  if (GEAR_RACQUET_COMPONENT_TYPES.includes(type)) {
    return racquetTypeLabelMap[type] ? racquetTypeLabelMap[type](t) : type
  }
  return type
}

export function getGearRacquetComponentAvatar(type) {
  if (GEAR_RACQUET_COMPONENT_TYPES.includes(type)) {
    return racquetTypeAvatarMap[type] || ''
  }
  return ''
}

export function getGearWindsurfComponentType(type, t) {
  if (GEAR_WINDSURF_COMPONENT_TYPES.includes(type)) {
    return windsurfTypeLabelMap[type] ? windsurfTypeLabelMap[type](t) : type
  }
  return type
}

export function getGearWindsurfComponentAvatar(type) {
  if (GEAR_WINDSURF_COMPONENT_TYPES.includes(type)) {
    return windsurfTypeAvatarMap[type] || ''
  }
  return ''
}
