from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
)
import requests
import datetime
from garth.exc import GarthHTTPError
import os
from getpass import getpass

email = os.getenv("EMAIL")
password = os.getenv("PASSWORD")
tokenstore = os.getenv("GARMINTOKENS") or ".garminconnect"
api = None
today = datetime.date.today()


def get_date():
    """Get date from user input."""

    return input("Enter date (dd-mm-yyyy): ")


def get_credentials():
    """Get user credentials."""

    email = input("Login e-mail: ")
    password = getpass("Enter password: ")

    return email, password


def get_mfa():
    """Get MFA."""

    return input("MFA one-time code: ")


def init_api(email, password):
    """Initialize Garmin API with your credentials."""

    try:
        # Using Oauth1 and OAuth2 token files from directory
        print(
            f"Trying to login to Garmin Connect using token data from directory '{tokenstore}'...\n"
        )

        garmin = Garmin()
        garmin.login(tokenstore)

    except (FileNotFoundError, GarthHTTPError, GarminConnectAuthenticationError):
        # Session is expired. You'll need to log in again
        print(
            "Login tokens not present, login with your Garmin Connect credentials to generate them.\n"
            f"They will be stored in '{tokenstore}' for future use.\n"
        )
        try:
            # Ask for credentials if not set as environment variables
            if not email or not password:
                email, password = get_credentials()

            garmin = Garmin(
                email=email, password=password, is_cn=False, prompt_mfa=get_mfa
            )
            garmin.login()
            # Save Oauth1 and Oauth2 token files to directory for next login
            garmin.garth.dump(tokenstore)
            print(
                f"Oauth tokens stored in '{tokenstore}' directory for future use. (first method)\n"
            )
        except (
            FileNotFoundError,
            GarthHTTPError,
            GarminConnectAuthenticationError,
            requests.exceptions.HTTPError,
        ) as err:
            print(err)
            return None

    return garmin


date = get_date()
date_object = datetime.datetime.strptime(date, "%d-%m-%Y")
date_string = date_object.strftime("%Y-%m-%d")

if not api:
    api = init_api(email, password)

if api:
    garmin_bc = api.get_body_composition(date_string, date_string)
    garmin_ds = api.get_daily_steps("2025-11-01", "2025-11-24")
    garmin_us = api.get_user_summary(date_string)
    garmin_stats_and_db = api.get_stats_and_body(date_string)

    if (
        garmin_ds is None
        or "totalSteps" not in garmin_ds[0]
        or not garmin_ds[0]["totalSteps"]
    ):
        # Log an informational event if no daily steps were found
        print("garmin_ds is None or empty")

    print(garmin_ds)


""" {
    "userProfileId": 12345678,
    "totalKilocalories": 1999.0,
    "activeKilocalories": 61.0,
    "bmrKilocalories": 1938.0,
    "wellnessKilocalories": 1999.0,
    "burnedKilocalories": None,
    "consumedKilocalories": None,
    "remainingKilocalories": 1881.0,
    "totalSteps": 6887,
    "netCalorieGoal": 1820,
    "totalDistanceMeters": 5351,
    "wellnessDistanceMeters": 5351,
    "wellnessActiveKilocalories": 61.0,
    "netRemainingKilocalories": 1881.0,
    "userDailySummaryId": 12345678,
    "calendarDate": "2025-11-16",
    "rule": {"typeId": 4, "typeKey": "groups"},
    "uuid": "00000000-0000-0000-0000-000000000000",
    "dailyStepGoal": 7050,
    "wellnessStartTimeGmt": "2025-11-16T00:00:00.0",
    "wellnessStartTimeLocal": "2025-11-16T00:00:00.0",
    "wellnessEndTimeGmt": "2025-11-17T00:00:00.0",
    "wellnessEndTimeLocal": "2025-11-17T00:00:00.0",
    "durationInMilliseconds": 86400000,
    "wellnessDescription": None,
    "highlyActiveSeconds": 356,
    "activeSeconds": 2405,
    "sedentarySeconds": 51322,
    "sleepingSeconds": 32317,
    "includesWellnessData": True,
    "includesActivityData": False,
    "includesCalorieConsumedData": False,
    "privacyProtected": False,
    "moderateIntensityMinutes": 0,
    "vigorousIntensityMinutes": 0,
    "floorsAscendedInMeters": 38.693,
    "floorsDescendedInMeters": 26.818,
    "floorsAscended": 12.69455,
    "floorsDescended": 8.79856,
    "intensityMinutesGoal": 400,
    "userFloorsAscendedGoal": 10,
    "minHeartRate": 41,
    "maxHeartRate": 96,
    "restingHeartRate": 42,
    "lastSevenDaysAvgRestingHeartRate": 44,
    "source": "GARMIN",
    "averageStressLevel": 23,
    "maxStressLevel": 89,
    "stressDuration": 22320,
    "restStressDuration": 41160,
    "activityStressDuration": 15660,
    "uncategorizedStressDuration": 7260,
    "totalStressDuration": 86400,
    "lowStressDuration": 17040,
    "mediumStressDuration": 4620,
    "highStressDuration": 660,
    "stressPercentage": 25.83,
    "restStressPercentage": 47.64,
    "activityStressPercentage": 18.12,
    "uncategorizedStressPercentage": 8.4,
    "lowStressPercentage": 19.72,
    "mediumStressPercentage": 5.35,
    "highStressPercentage": 0.76,
    "stressQualifier": "BALANCED",
    "measurableAwakeDuration": 46980,
    "measurableAsleepDuration": 32160,
    "lastSyncTimestampGMT": None,
    "minAvgHeartRate": 41,
    "maxAvgHeartRate": 93,
    "bodyBatteryChargedValue": 77,
    "bodyBatteryDrainedValue": 66,
    "bodyBatteryHighestValue": 100,
    "bodyBatteryLowestValue": 25,
    "bodyBatteryMostRecentValue": 37,
    "bodyBatteryDuringSleep": 75,
    "bodyBatteryAtWakeTime": 100,
    "bodyBatteryVersion": 3.0,
    "abnormalHeartRateAlertsCount": None,
    "averageSpo2": 96.0,
    "lowestSpo2": 86,
    "latestSpo2": 98,
    "latestSpo2ReadingTimeGmt": "2025-11-17T00:00:00.0",
    "latestSpo2ReadingTimeLocal": "2025-11-17T00:00:00.0",
    "averageMonitoringEnvironmentAltitude": -3.0,
    "restingCaloriesFromActivity": None,
    "bodyBatteryDynamicFeedbackEvent": {
        "eventTimestampGmt": "2025-11-16T21:00:17",
        "bodyBatteryLevel": "HIGH",
        "feedbackShortType": "SLEEP_PREPARATION_BALANCED_AND_INACTIVE",
        "feedbackLongType": "SLEEP_PREPARATION_BALANCED_AND_INACTIVE",
    },
    "endOfDayBodyBatteryDynamicFeedbackEvent": {
        "eventTimestampGmt": "2025-11-16T00:30:16",
        "bodyBatteryLevel": "HIGH",
        "feedbackShortType": "SLEEP_TIME_PASSED_STRESSFUL_AND_INACTIVE",
        "feedbackLongType": "SLEEP_TIME_PASSED_STRESSFUL_AND_INACTIVE",
    },
    "bodyBatteryActivityEventList": [
        {
            "eventType": "SLEEP",
            "eventStartTimeGmt": "2025-11-16T00:12:05",
            "timezoneOffset": 0,
            "durationInMilliseconds": 32040000,
            "bodyBatteryImpact": 75,
            "feedbackType": "NONE",
            "shortFeedback": "NONE",
            "deviceId": 1234567890,
            "activityName": None,
            "activityType": None,
            "activityId": None,
            "eventUpdateTimeGmt": "2025-11-16T09:15:23",
        }
    ],
    "avgWakingRespirationValue": 13.0,
    "highestRespirationValue": 19.0,
    "lowestRespirationValue": 6.0,
    "latestRespirationValue": 11.0,
    "latestRespirationTimeGMT": "2025-11-17T00:00:00.0",
    "respirationAlgorithmVersion": 200,
    "from": 1763251200000,
    "until": 1763337599999,
    "weight": 68199.0,
    "bmi": None,
    "bodyFat": None,
    "bodyWater": None,
    "boneMass": None,
    "muscleMass": None,
    "physiqueRating": None,
    "visceralFat": None,
    "metabolicAge": None,
} """
