# Importing data

Endurain allows users to upload individual files via the web interface for easy web-based importing.  

If a user wants to import multiple files at the same time, there are two bulk import options currently available:
- *Generic bulk import* - Allows users to import data from activity-containing files such as .fit or .gpx.
- *Importing from a Strava bulk export* - Allows users to import gear, activities, activity metadata, and media from a Strava bulk export.

Both of these options currently require placing files on the server directly. Read on to learn more about these two import options.

## Generic bulk import and file upload

To perform a generic bulk import:
- Place .fit, .tcx, .gz and/or .gpx files into the data/activity_files/bulk_import folder. Create the folder if needed.
- In the "Settings" menu select "Import".
- Click "Import activities" next to "Bulk Import".
- Check the logs for detailed messages regarding the import.

### Notes on the generic bulk import

.fit files are preferred. I noticed that Strava/Garmin Connect process of converting .fit to .gpx introduces additional data to the activity file leading to minor variances in the data, like for example additional meters in distance and elevation gain. 

**There is currently no mechanism to undo or revert an import.**  Thus, we advise backing up your database before importing if you have any doubts about the process or whether duplicates exist. 

After the files are processed, the files are renamed and moved. Activity files that were successfully imported will be renamed and moved to the data/activity_files/processed directory. Files that resulted in an error during import should be moved to the data/activity_files/bulk_import/import_errors folder.

The generic bulk import currently only imports data contained in the .fit, .tcx or .gpx files - no external metadata or other media are imported.

While each file present in the import directory will only be imported once (and then moved to a storage directory), the bulk import does not check for duplicates while importing. Thus, activities that are already present in Endurain will be imported again (and will default be hidden if their start time matches an existing activity's start time, with a notification prompting the user to review).

GEOCODES API has a limit of 1 Request/Second on the free plan, so if you have a large number of files, it might not be possible to import all in the same action

## Importing data from a Strava bulk export (BETA)

Strava allows users to create a bulk export of their historical activity from the Strava website.  This exported information is stored in a zip file, primarily as .csv files, GPS recording files (e.g., .gpx, .fit), and media files (e.g., .jpg, .png). Currently, the import script only works for English .csv files. If you're using a different language, please switch your Strava profile to English before bulk exporting.

All Strava bulk import functions expect files in the data/activity_files/strava_import folder. Create the folder if needed.

Recommended procedure for importing a Strava bulk export:
1. Read the instructions below, including notes on limitations and known issues.
2. Backup your database and other core files.  There is currently no mechanism to roll-back or undo a bulk import.
3. Import, or manually create, any gear that was present in Strava.
4. Import activities and media that were in Strava, ideally performing a small test import first.

### Importing gear from a Strava bulk export

Importing of bikes and shoes is currently possible. Bike and shoe imports are screened for duplicates via nickname, so pre-existing gear with the same nickname will prevent import of that item of gear (case-insensitively).

#### Bikes import

At the present time, importing bikes from a Strava bulk export is implemented as a beta feature, use with caution. Components of bikes are not imported, just the bikes themselves. 

To perform an import of bikes: 
- Place the bikes.csv file from a Strava bulk export into the data/activity_files/strava_import folder. Create the folder if needed.
- In the "Settings" menu select "Import".
- Click "Bikes Import" next to "Strava gear import".
- Upon successful import, the shoes.csv file is moved to /data/activity_files/processed folder.
- Status messages about the import, including why any gear was not imported, can be found in the logs.

Ensure the file is named "bikes.csv" and has a header row with at least the fields 'Bike Name', 'Bike Brand', and 'Bike Model'.

#### Shoe import

At the present time, importing shoes from a Strava bulk export is implemented as a beta feature, use with caution.  Components of shoes are not imported, just the shoes themselves. 

To perform an import of shoes: 
- Place the shoes.csv file from a Strava bulk export into the data/activity_files/strava_import folder. Create the folder if needed.
- In the "Settings" menu select "Import".
- Click "Shoes import" next to "Strava gear import".
- Upon successful import, the shoes.csv file is moved to /data/activity_files/processed folder.
- Status messages about the import, including why any gear was not imported, can be found in the logs.

Ensure the file is named "shoes.csv" and has a header row with at least the fields 'Shoe Name', 'Shoe Brand', and 'Shoe Model'.

Strava allows shoe names to be blank, but Endurain does not. Thus, shoes with a blank name will be renamed "Unnamed shoe X".

#### Notes on importing gear

IMPORTANT: There is currently no mechanism to undo a gear import.

All gear will be imported as active, as Strava does not export the active/inactive status of the gear.

Note that Endurain does not allow the `+` character in gear field names, and thus +'s will removed from all fields and replaced with spaces (" ") on import.  All beginning and ending space characters (" ") will be removed on import as well.

Endurain does not allow duplicate gear nicknames, case insensitively (e.g., `Ilves` and `ilves` would not be allowed) and regardless of gear type (e.g., `Ilves` the bike and `ilves` the shoe would not be allowed). Gear with duplicate nicknames will not be imported (i.e., only the first item with a given nickname will be imported).

The import routine checks for duplicate items, and should not import duplicates. Thus it should be safe to re-import the same file multiple times. However, due to the renaming of un-named shoes, repeated imports of the same shoe file will create duplicate entries of any unnamed shoes present. 

Gear that is already present in Endurain due to having an active link with Strava will not be imported via the manual import process.

### Importing activities and media from a Strava bulk export

At the present time, importing activities and media from a Strava bulk export is implemented as a very early beta feature that has undergone only limited testing, use with extreme caution. Please read the entire section below, especially the limitations. Currently, only images can be imported, not videos.

**We advise backing up your database, or using a test install of Endurain, before importing data.  There is currently no mechanism to undo or revert an import.**

To perform an import of activities and media: 
- Place the extracted contents of a Strava bulk export .zip file in the data/activity_files/strava_import folder. Create the folder if needed. 
- Consider performing a test import before attempting to import a large set of files; see notes below on how to do this.
- If you want imported activities to be linked to gear (bikes or shoes), ensure that any bikes or shoes referred to in activities are already present in Endurain before importing the activities. 
- In the "Settings" menu select "Import".
- Click "Strava bulk import" next to "Strava bulk import (Beta)".
- Status messages about the import, including progress messages and why any activities or media were not imported, can be found in the logs.

In addition to the base activity track and statistics, the Strava bulk import feature should also import each activity's title, description, activity type, gear (if it exists already in Endurain), Strava activity ID (into a non-displayed database field), and media. 

The structure of files expected is:
- an activities.csv file in the data/activity_files/strava_import folder (required)
- activities files in the data/activity_files/strava_import/activities folder (required)
- media files in the data/activity_files/strava_import/media folder (optional, if you want media imported)

The activities.csv file requires a header row with at least the following fields: 'Filename', 'Activity Date', 'Activity Description', 'Activity Gear', 'Activity ID', 'Activity Name', 'Activity Type', and 'Media'.

Activity files that were successfully imported will be renamed and moved to the data/activity_files/processed directory, and media files moved to the data/activity_media folder. 

Activity files that resulted in an error during import should be moved to the data/strava_import/activities/import_errors folder

#### Performing a test import

You may import as many or as few activities as you want during any given import by placing only the activity files that you want imported into the data/strava_import/activities directory. The importer looks for importable (i.e., .gpx, .fit, etc.) files in the activities folder and only then looks to see if each file has importable metadata and/or media present in the activities.csv file.

Thus, to perform a test import:
- Place only a few activity files into the data/strava_import/activities folder.
- Place the full activities.csv, bikes.csv, shoes.csv, and media folder contents into their respective locations. 
- Perform an import as directed, above.
- Check the logs to watch the import progress and understand the results. 
- To watch the logs in Docker, you can run the command "docker logs -f --tail 20 container_name"

#### Strava bulk import limitations 

**IMPORTANT: We advise backing up your database, or using a test Endurain install, before importing data: There is currently no mechanism to undo or revert an import.**

Note that large imports may take many hours, depending on server hardware.  Watch the logs to see detailed information.

While each file present in the import directory will only be imported once (and then moved to a storage directory), the bulk import of Strava activities does not check for duplicates while importing. Thus, activities that are already present in Endurain will be imported again (and, if the start times match, be marked as hidden and a notification sent to the user).

The bulk import of Strava activities and media does not create gear.  Please import, or create, any gear referred to in the activities before importing the activities. Ensure the nickname and other details of the gear matches precisely.

If you had unnamed shoes in Strava, note that they will be renamed by the shoe gear import routine, and thus will not be matched with activities during a bulk activity import.  The best fix for this at the present time is, unfortunately, to edit the activities.csv file manually and add the new shoe name to the relevant rows in activities.csv (Strava formats shoe gear in the activities.csv file as: "{brand} {model} {name}").  Sorry.

Comments associated with media are not imported (Endurain does not currently allow comments on media). FYI: Comments associated with media are stored in Strava's media.csv file.

While notifications will be sent to the user as items are imported, it is advised to check the log for full detailed information on the import and its progress; logs (and the console) are updated as each file is processed. 