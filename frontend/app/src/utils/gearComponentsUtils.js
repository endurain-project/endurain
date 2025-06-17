
export function getGearComponentType(type, t) {
	const avatarMap = {
		"back_tire": t("gearComponentListComponent.gearComponentBackTire"),
		"front_tire": t("gearComponentListComponent.gearComponentFrontTire"),
	};

	return avatarMap[type];
}

export function getGearComponentAvatar(type) {
	const avatarMap = {
		"back_tire": "/src/assets/avatar/gearComponents/tire1.png",
		"front_tire": "/src/assets/avatar/gearComponents/tire1.png",
	};

	return avatarMap[type];
}