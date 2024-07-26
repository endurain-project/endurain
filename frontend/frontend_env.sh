#!/bin/sh
for i in $(env | grep MY_APP_)
do
	key=$(echo $i | cut -d '=' -f 1)
	value=$(echo $i | cut -d '=' -f 2-)
	echo $key=$value
    # sed All files
	# find /usr/share/nginx/html -type f -exec sed -i "s|${key}|${value}|g" '{}' +

    # sed JS and CSS only
    find /usr/share/nginx/html -type f \( -name '*.js' -o -name '*.css' \) -exec sed -i "s|${key}|${value}|g" '{}' +
done