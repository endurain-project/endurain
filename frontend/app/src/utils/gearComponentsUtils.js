
export function getGearComponentType(type, t) {
	const avatarMap = {
		"back_tire": t("gearComponentListComponent.gearComponentBackTire"),
		"front_tire": t("gearComponentListComponent.gearComponentFrontTire"),
		"cassette": t("gearComponentListComponent.gearComponentCassette"),
		"chain": t("gearComponentListComponent.gearComponentChain"),
	};

	return avatarMap[type];
}

export function getGearComponentAvatar(type) {
	const avatarMap = {
		"back_tire": "/src/assets/avatar/gearComponents/tire1.png",
		"front_tire": "/src/assets/avatar/gearComponents/tire1.png",
		"cassette": "/src/assets/avatar/gearComponents/cassette1.png",
		"chain": "/src/assets/avatar/gearComponents/chain1.png",
	};

	return avatarMap[type];
}