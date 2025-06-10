import gears.gear_components.schema as gear_components_schema


def serialize_gear_component(gear_component: gear_components_schema.GearComponents):
    # Serialize the gear_component object
    gear_component.purchase_date = gear_component.purchase_date.strftime("%Y-%m-%d")

    if gear_component.retired_date:
        gear_component.retired_date = gear_component.retired_date.strftime("%Y-%m-%d")

    # Return the serialized gear_component object
    return gear_component
