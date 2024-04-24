<template>
    <footer class="pb-3  mt-auto bg-body">
        <hr>
        <p class="text-center text-muted">&copy; {{ new Date().getFullYear() === 2023 ? '2023' : '2023 - ' + new Date().getFullYear() }} Endurain • <a href="https://github.com/joaovitoriasilva/endurain" role="button"><font-awesome-icon :icon="['fab', 'fa-github']" /></a> • <a href="https://fosstodon.org/@endurain"><font-awesome-icon :icon="['fab', 'fa-mastodon']" /></a> • v0.1.6</p>
        <p class="text-center text-muted"><img src="/src/assets/strava/api_logo_cptblWith_strava_horiz_light.png" alt="Compatible with STRAVA image" height="25" /></p>
    </footer>
</template>