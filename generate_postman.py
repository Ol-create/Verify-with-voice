import requests
import json

# URL of your running FastAPI app
OPENAPI_URL = "http://127.0.0.1:8000/openapi.json"

# Where to save the Postman collection
OUTPUT_FILE = "postman_collection.json"

def generate_postman_collection():
    response = requests.get(OPENAPI_URL)
    response.raise_for_status()
    openapi_schema = response.json()

    # Wrap in Postman collection format
    postman_collection = {
        "info": {
            "name": "My FastAPI Collection",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        },
        "item": []
    }

    # Convert each FastAPI path+method into a Postman request
    for path, methods in openapi_schema["paths"].items():
        for method, details in methods.items():
            postman_collection["item"].append({
                "name": f"{method.upper()} {path}",
                "request": {
                    "method": method.upper(),
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "url": {
                        "raw": f"http://127.0.0.1:8000{path}",
                        "protocol": "http",
                        "host": ["127", "0", "0", "1"],
                        "port": "8000",
                        "path": path.strip("/").split("/")
                    }
                }
            })

    with open(OUTPUT_FILE, "w") as f:
        json.dump(postman_collection, f, indent=2)

    print(f"✅ Postman collection saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_postman_collection()
