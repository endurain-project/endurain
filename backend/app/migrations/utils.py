from sqlalchemy.orm import Session

import migrations.crud as migrations_crud
import migrations.migration_1 as migrations_migration_1
import migrations.migration_2 as migrations_migration_2
import migrations.migration_3 as migrations_migration_3
import migrations.migration_4 as migrations_migration_4
import migrations.migration_5 as migrations_migration_5
import migrations.migration_6 as migrations_migration_6

import core.logger as core_logger


async def check_migrations_not_executed(db: Session):
    migrations_not_executed = migrations_crud.get_migrations_not_executed(db)

    if migrations_not_executed:
        for migration in migrations_not_executed:
            # Log the migration not executed
            core_logger.print_to_log(
                f"Migration not executed: {migration.name} - Migration will be executed"
            )

            if migration.id == 1:
                # Execute the migration
                migrations_migration_1.process_migration_1(db)

            if migration.id == 2:
                # Execute the migration
                migrations_migration_2.process_migration_2(db)

            if migration.id == 3:
                # Execute the migration
                migrations_migration_3.process_migration_3(db)

            if migration.id == 4:
                # Execute the migration
                await migrations_migration_4.process_migration_4(db)

            if migration.id == 5:
                # Execute the migration
                await migrations_migration_5.process_migration_5(db)

            if migration.id == 6:
                # Execute the migration
                migrations_migration_6.process_migration_6(db)
