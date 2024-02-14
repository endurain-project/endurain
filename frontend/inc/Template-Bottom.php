                <!-- Footer -->
                <footer class="border-top py-3 my-4 bg-body-tertiar">
                        <p class="text-center text-muted">&copy;
                                <?php if (date("Y") == 2023) {
                                        echo date("Y");
                                } else { ?>2023 -
                                        <?php echo date("Y");
                                } ?> Endurain • <a href="https://github.com/joaovitoriasilva/endurain"
                                        role="button"><i class="fa-brands fa-github"></i></a> • <a href="https://fosstodon.org/@endurain"><i class="fa-brands fa-mastodon"></i></a> • v0.1.5
                        </p>
                        <p class="text-center text-muted"><img src="../img/strava/api_logo_cptblWith_strava_horiz_light.png"
                                        alt="Compatible with STRAVA image" height="25" /></p>
                </footer>
        </body>
</html>