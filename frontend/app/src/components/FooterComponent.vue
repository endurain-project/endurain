<template>
    <footer class="py-5 bg-body-tertiary">
        <div class="container">
            <p class="text-center text-muted">&copy; {{ new Date().getFullYear() === 2023 ? '2023' : '2023 - ' + new Date().getFullYear() }} Endurain • <a class="link-body-emphasis" href="https://github.com/joaovitoriasilva/endurain" role="button"><font-awesome-icon :icon="['fab', 'fa-github']" /></a> • <a class="link-body-emphasis" href="https://docs.endurain.com"><font-awesome-icon :icon="['fas', 'book']" /></a> • <a class="link-body-emphasis" href="https://fosstodon.org/@endurain"><font-awesome-icon :icon="['fab', 'fa-mastodon']" /></a> • <a class="link-body-emphasis" href="https://discord.gg/6VUjUq2uZR"><font-awesome-icon :icon="['fab', 'fa-discord']" /></a> • v0.10.6</p>
            <p class="text-center text-muted"><img src="/src/assets/strava/api_logo_cptblWith_strava_horiz_light.png" alt="Compatible with STRAVA image" height="25" /> • <img src="/src/assets/garminconnect/Garmin_connect_badge_print_RESOURCE_FILE-01.png" alt="Works with Garmin Connect image" height="25" /></p>
        </div>
    </footer>
</template>