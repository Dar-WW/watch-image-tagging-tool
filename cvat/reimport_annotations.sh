#!/bin/bash
# Re-import annotations with correct format

if [ -z "$1" ]; then
    echo "Usage: $0 <password>"
    exit 1
fi

PASSWORD="$1"

# Login and get session cookie and CSRF token
COOKIES=$(mktemp)
curl -s -c "$COOKIES" -X POST http://localhost:8080/api/auth/login \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"dar\",\"password\":\"$PASSWORD\"}" > /dev/null

COOKIE=$(grep sessionid "$COOKIES" | awk '{print $7}')
CSRF=$(grep csrftoken "$COOKIES" | awk '{print $7}')

if [ -z "$COOKIE" ] || [ -z "$CSRF" ]; then
    echo "Login failed"
    cat "$COOKIES"
    rm "$COOKIES"
    exit 1
fi

echo "Logged in successfully"
echo "Session: ${COOKIE:0:20}..."
echo "CSRF: ${CSRF:0:20}..."

echo "Re-importing annotations with format 'cvat'..."

# Re-import annotations for each task
TASK_ID=1
for xml_file in cvat_exports/*_annotations.xml; do
    WATCH_NAME=$(basename "$xml_file" _annotations.xml)
    echo "  Task $TASK_ID: $WATCH_NAME"
    
    RESULT=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X PUT "http://localhost:8080/api/tasks/$TASK_ID/annotations?format=CVAT%201.1" \
        -H "X-CSRFToken: $CSRF" \
        -b "sessionid=$COOKIE;csrftoken=$CSRF" \
        -F "annotation_file=@$xml_file")
    
    HTTP_CODE=$(echo "$RESULT" | grep "HTTP_CODE" | cut -d: -f2)
    BODY=$(echo "$RESULT" | grep -v "HTTP_CODE")
    
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ] || [ "$HTTP_CODE" = "202" ]; then
        echo "    ✓ Imported (HTTP $HTTP_CODE)"
    else
        echo "    ✗ Failed (HTTP $HTTP_CODE): $BODY"
    fi
    
    TASK_ID=$((TASK_ID + 1))
done

rm "$COOKIES"
echo "Done"
