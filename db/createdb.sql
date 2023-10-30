SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='TRADITIONAL,ALLOW_INVALID_DATES';

CREATE SCHEMA IF NOT EXISTS `gearguardian` DEFAULT CHARACTER SET utf8 COLLATE utf8_general_ci ;
USE `gearguardian`;

-- -----------------------------------------------------
-- Table `gearguardian`.`users`
-- -----------------------------------------------------
CREATE  TABLE IF NOT EXISTS `gearguardian`.`users` (
  `id` INT(10) NOT NULL AUTO_INCREMENT ,
  `name` VARCHAR(45) NOT NULL COMMENT 'User real name (May include spaces)' ,
  `username` VARCHAR(45) NOT NULL UNIQUE COMMENT 'User username (letters, numbers and dots allowed)' ,
  `email` VARCHAR(250) NOT NULL UNIQUE COMMENT 'User email (max 45 characteres)' ,
  `password` VARCHAR(100) NOT NULL COMMENT 'User password (hash)' ,
  `city` VARCHAR(45) NULL COMMENT 'User city' ,
  `birthdate` DATE NULL COMMENT 'User birthdate (data)' ,
  `preferred_language` VARCHAR(5) NOT NULL COMMENT 'User preferred language (en, pt, others)' ,
  `gender` INT(1) NOT NULL COMMENT 'User gender (one digit)(1 - male, 2 - female)' ,
  `access_type` INT(1) NOT NULL COMMENT 'User type (one digit)(1 - regular user, 2 - admin)' ,
  `photo_path` VARCHAR(250) NULL COMMENT 'User photo path' ,
  `photo_path_aux` VARCHAR(250) NULL COMMENT 'Auxiliar photo path' ,
  `is_active` INT(1) NOT NULL COMMENT 'Is user active (0 - not active, 1 - active)' ,
  `strava_token` VARCHAR(250) NULL ,
  `strava_refresh_token` VARCHAR(250) NULL ,
  `strava_token_expires_at` DATETIME NULL ,
  PRIMARY KEY (`id`) )
ENGINE = InnoDB;

-- -----------------------------------------------------
-- Create default admin user
-- -----------------------------------------------------
INSERT INTO `gearguardian`.`users` (`id`,`name`,`username`,`password`,`email`,`preferred_language`,`gender`,`access_type`,`is_active`) VALUES (1,'Administrator','admin','d31e6a23d06bb2ca18ad612a596be36183b8e302ba3aa583384e305b279ab9e7',"joao.vitoria.silva@pm.me","en",1,2,1);

-- -----------------------------------------------------
-- Table `gearguardian`.`access_tokens`
-- -----------------------------------------------------
CREATE  TABLE IF NOT EXISTS `gearguardian`.`access_tokens` (
  `id` INT(10) NOT NULL AUTO_INCREMENT ,
  `token` VARCHAR(256) NOT NULL COMMENT 'User token' ,
  `user_id` INT(10) NOT NULL COMMENT 'User ID that the token belongs' ,
  `created_at` DATETIME NOT NULL COMMENT 'Token creation date (date)' ,
  `expires_at` DATETIME NOT NULL COMMENT 'Token expiration date (date)' ,
  PRIMARY KEY (`id`) ,
  INDEX `FK_user_id_idx` (`user_id` ASC) ,
  CONSTRAINT `FK_token_user`
    FOREIGN KEY (`user_id` )
    REFERENCES `gearguardian`.`users` (`id` )
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;

-- -----------------------------------------------------
-- Table `gearguardian`.`gear`
-- -----------------------------------------------------
CREATE  TABLE IF NOT EXISTS `gearguardian`.`gear` (
  `id` INT(10) NOT NULL AUTO_INCREMENT ,
  `brand` VARCHAR(45) NULL COMMENT 'Gear brand (May include spaces)' ,
  `model` VARCHAR(45) NULL COMMENT 'Gear model (May include spaces)' ,
  `nickname` VARCHAR(45) NOT NULL COMMENT 'Gear nickname (May include spaces)' ,
  `gear_type` INT(1) NOT NULL COMMENT 'Gear type (1 - bike, 2 - shoes, 3 - wetsuit)' ,
  `user_id` INT(10) NOT NULL COMMENT 'User ID that the token belongs' ,
  `created_at` DATETIME NOT NULL COMMENT 'Gear creation date (date)' ,
  `is_active` INT(1) NOT NULL COMMENT 'Is gear active (0 - not active, 1 - active)' ,
  PRIMARY KEY (`id`) ,
  INDEX `FK_user_id_idx` (`user_id` ASC) ,
  CONSTRAINT `FK_gear_user`
    FOREIGN KEY (`user_id` )
    REFERENCES `gearguardian`.`users` (`id` )
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;

-- -----------------------------------------------------
-- Table `gearguardian`.`user_settings`
-- -----------------------------------------------------
CREATE  TABLE IF NOT EXISTS `gearguardian`.`user_settings` (
  `id` INT(10) NOT NULL AUTO_INCREMENT ,
  `user_id` INT(10) NOT NULL COMMENT 'User ID that the activity belongs' ,
  `activity_type` INT(2) NULL COMMENT 'Gear type' ,
  `gear_id` INT(10) NULL COMMENT 'Gear ID associated with this activity' ,
  PRIMARY KEY (`id`) ,
  INDEX `FK_user_id_idx` (`user_id` ASC) ,
  CONSTRAINT `FK_user_settings_user`
    FOREIGN KEY (`user_id` )
    REFERENCES `gearguardian`.`users` (`id` )
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  INDEX `FK_gear_id_idx` (`gear_id` ASC) ,
  CONSTRAINT `FK_user_settings_gear`
    FOREIGN KEY (`gear_id` )
    REFERENCES `gearguardian`.`gear` (`id` )
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;

-- -----------------------------------------------------
-- Table `gearguardian`.`activities`
-- -----------------------------------------------------
CREATE  TABLE IF NOT EXISTS `gearguardian`.`activities` (
  `id` INT(10) NOT NULL AUTO_INCREMENT ,
  `user_id` INT(10) NOT NULL COMMENT 'User ID that the activity belongs' ,
  `name` VARCHAR(45) NULL COMMENT 'Activity name (May include spaces)' ,
  `distance` INT(9) NOT NULL COMMENT 'Distance in meters' ,
  `activity_type` INT(2) NOT NULL COMMENT 'Gear type' ,
  `start_time` DATETIME NOT NULL COMMENT 'Actvitiy start date (datetime)' ,
  `end_time` DATETIME NOT NULL COMMENT 'Actvitiy end date (datetime)' ,
  `city` VARCHAR(45) NULL COMMENT 'Activity city (May include spaces)' ,
  `town` VARCHAR(45) NULL COMMENT 'Activity town (May include spaces)' ,
  `country` VARCHAR(45) NULL COMMENT 'Activity country (May include spaces)' ,
  `created_at` DATETIME NOT NULL COMMENT 'Actvitiy creation date (datetime)' ,
  `waypoints` LONGTEXT NULL COMMENT 'Store waypoints data',
  `elevation_gain` INT(5) NOT NULL COMMENT 'Elevation gain in meters' ,
  `elevation_loss` INT(5) NOT NULL COMMENT 'Elevation loss in meters' ,
  `pace` DECIMAL(20, 10) NOT NULL COMMENT 'Pace seconds per meter (s/m)' ,
  `gear_id` INT(10) NULL COMMENT 'Gear ID associated with this activity' ,
  PRIMARY KEY (`id`) ,
  INDEX `FK_user_id_idx` (`user_id` ASC) ,
  CONSTRAINT `FK_activity_user`
    FOREIGN KEY (`user_id` )
    REFERENCES `gearguardian`.`users` (`id` )
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  INDEX `FK_gear_id_idx` (`gear_id` ASC) ,
  CONSTRAINT `FK_activity_gear`
    FOREIGN KEY (`gear_id` )
    REFERENCES `gearguardian`.`gear` (`id` )
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,)
ENGINE = InnoDB;

-- -----------------------------------------------------
-- Table `gearguardian`.`components`
-- -----------------------------------------------------
CREATE  TABLE IF NOT EXISTS `gearguardian`.`component` (
  `id` INT(10) NOT NULL AUTO_INCREMENT ,
  `brand` VARCHAR(45) NULL COMMENT 'Component brand (May include spaces)' ,
  `model` VARCHAR(45) NULL COMMENT 'Component piece model (May include spaces)' ,
  `nickname` VARCHAR(45) NOT NULL COMMENT 'Component piece nickname (May include spaces)' ,
  `component_type` INT(1) NOT NULL COMMENT 'Component type (1 - wheels, 2 - tires, 3 - cassette, 4 - chain, 5 - brake rotors, 6 - brake pads, 7 - inner tubes)' ,
  `component_subtype` INT(2) NULL COMMENT 'Component sub type (1 - front wheel, 2 - back wheel, 3 - front tire, 4 - back tire, 5 - front rotor, 6 - back rotor, 7 - front brake pad, 8 - back brake pad, 9 - front inner tube, 10 - back inner tube)' ,
  `gear_id` INT(10) NOT NULL COMMENT 'User ID that the token belongs' ,
  `created_at` DATETIME NOT NULL COMMENT 'Component creation date (date)' ,
  `is_active` INT(1) NOT NULL COMMENT 'Is component active (0 - not active, 1 - active)' ,
  PRIMARY KEY (`id`) ,
  INDEX `FK_gear_id_idx` (`gear_id` ASC) ,
  CONSTRAINT `FK_component_gear`
    FOREIGN KEY (`gear_id` )
    REFERENCES `gearguardian`.`gear` (`id` )
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;

USE `gearguardian` ;

SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;