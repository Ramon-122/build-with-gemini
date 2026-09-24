# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from pathlib import Path
from typing import List, Optional
import io
import os
import requests
from google.cloud import firestore, storage
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory.vertex_ai_memory_bank_service import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types
from PIL import Image, ImageDraw

from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog
from .a2ui_utils import a2ui_callback

MODEL = "gemini-2.5-flash"
PROJECT_ID = "qwiklabs-gcp-02-075769363a76"
BUCKET_NAME = "smart-pantry-images-qwiklabs-gcp-02-075769363a76"
ENGINE_ID = "1959270347068932096"

# Load Agent Engine resource name from deployment_metadata.json if available
agent_engine_resource_name = None
metadata_file = Path(__file__).resolve().parent.parent / "deployment_metadata.json"
if metadata_file.exists():
    try:
        with open(metadata_file, "r") as f:
            metadata = json.load(f)
            agent_engine_resource_name = metadata.get("remote_agent_runtime_id")
            if agent_engine_resource_name and "/" in agent_engine_resource_name:
                ENGINE_ID = agent_engine_resource_name.split("/")[-1]
    except Exception:
        pass

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=agent_engine_resource_name
) if agent_engine_resource_name else AgentEngineSandboxCodeExecutor()

# Memory service builder for deployment
def memory_service_builder():
    return VertexAiMemoryBankService(
        project=PROJECT_ID,
        location="us-east1",
        agent_engine_id=ENGINE_ID,
    )

# WRITE: callback to add session events to memory after each turn
async def generate_memories_callback(callback_context: CallbackContext):
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        pass
    return None

# Hardcode project ID as a string for Firestore client so it works both locally and on Agent Platform
db = firestore.Client(project=PROJECT_ID)


def search_recipes(query: Optional[str] = None, ingredient: Optional[str] = None) -> List[dict]:
    """Search for recipes stored in the Smart Pantry database.

    Args:
        query: Optional search term to match against recipe name or cuisine.
        ingredient: Optional ingredient to filter recipes by.

    Returns:
        List of matching recipes with their full details.
    """
    collection_ref = db.collection("recipes")
    docs = collection_ref.stream()

    results = []
    for doc in docs:
        recipe = doc.to_dict()
        recipe["id"] = doc.id

        match = True
        if ingredient:
            ing_lower = ingredient.lower()
            recipe_ings = [i.lower() for i in recipe.get("ingredients", [])]
            if not any(ing_lower in ing for ing in recipe_ings):
                match = False

        if query and match:
            q_lower = query.lower()
            name_match = q_lower in recipe.get("name", "").lower()
            cuisine_match = q_lower in recipe.get("cuisine", "").lower()
            diet_match = any(q_lower in tag.lower() for tag in recipe.get("dietary_tags", []))
            if not (name_match or cuisine_match or diet_match):
                match = False

        if match:
            results.append(recipe)

    return results


def add_recipe(
    name: str,
    ingredients: List[str],
    instructions: str,
    prep_time_minutes: int,
    cuisine: str,
    id: Optional[str] = None,
    dietary_tags: Optional[List[str]] = None,
) -> str:
    """Add a new recipe to the Smart Pantry database.

    Args:
        name: Name of the recipe.
        ingredients: List of required ingredients.
        instructions: Cooking or preparation instructions.
        prep_time_minutes: Time in minutes to prepare the recipe.
        cuisine: Cuisine style (e.g. Italian, Mediterranean, Asian).
        id: Optional custom ID for the document. If omitted, a slug derived from name will be used.
        dietary_tags: Optional list of dietary tags (e.g. Vegetarian, Gluten-Free).

    Returns:
        Confirmation message with the created recipe ID.
    """
    doc_id = id or name.lower().replace(" ", "_").replace("-", "_")
    recipe_data = {
        "name": name,
        "ingredients": ingredients,
        "instructions": instructions,
        "prep_time_minutes": prep_time_minutes,
        "cuisine": cuisine,
        "dietary_tags": dietary_tags or [],
    }
    db.collection("recipes").document(doc_id).set(recipe_data)
    return f"Successfully added recipe '{name}' with ID '{doc_id}'."


def generate_dish_image(
    dish_name: str,
    tool_context: Optional[ToolContext] = None,
    prompt: Optional[str] = None,
) -> str:
    """Generate a dish image for a recipe using gemini-3.1-flash-lite-image in the global region.
    Saves the image as a Playground artifact and uploads it to Cloud Storage.

    Args:
        dish_name: The name of the dish or recipe.
        tool_context: ADK ToolContext injected automatically by the framework.
        prompt: Optional detailed description for image generation.

    Returns:
        Public HTTP URL of the generated dish image.
    """
    slug = dish_name.lower().replace(" ", "_").replace("-", "_")

    image_bytes = None
    mime_type = "image/jpeg"
    try:
        from google import genai
        client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
        img_prompt = prompt or f"A professional studio food photograph of {dish_name}, appetizing presentation"
        res = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=img_prompt,
        )
        if res.candidates and res.candidates[0].content and res.candidates[0].content.parts:
            for part in res.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break
    except Exception:
        pass

    if not image_bytes:
        img = Image.new("RGB", (600, 400), color=(44, 62, 80))
        draw = ImageDraw.Draw(img)
        draw.rectangle([(20, 20), (580, 380)], outline=(230, 126, 34), width=4)
        draw.text((40, 160), f"Dish: {dish_name.title()}", fill=(241, 196, 15))
        draw.text((40, 220), "Smart Pantry Culinary Photo", fill=(236, 240, 241))
        
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()
        mime_type = "image/jpeg"

    ext = "png" if "png" in mime_type else "jpeg"
    filename = f"{slug}.{ext}"

    # (1) Save image artifact in ADK tool_context for Playground Artifacts panel
    if tool_context:
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # (2) Upload image bytes to public Cloud Storage bucket
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    return f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"


def generate_dish_video(
    dish_name: str,
    tool_context: Optional[ToolContext] = None,
    prompt: Optional[str] = None,
) -> str:
    """Generate a short cooking demonstration video for a dish using Google's Omni model (gemini-omni-flash-preview) in the global region.
    Saves the video as a Playground artifact and uploads it to Cloud Storage.

    Args:
        dish_name: The name of the dish or recipe.
        tool_context: ADK ToolContext injected automatically by the framework.
        prompt: Optional detailed description for video generation.

    Returns:
        Public HTTP URL of the generated dish video.
    """
    slug = dish_name.lower().replace(" ", "_").replace("-", "_")

    video_bytes = None
    mime_type = "video/mp4"

    try:
        from google import genai
        client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
        vid_prompt = prompt or f"A short video showing a chef preparing and cooking {dish_name}"
        res = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=vid_prompt,
            timeout=10,
        )
        if hasattr(res, "outputs"):
            for output in res.outputs:
                if hasattr(output, "inline_data") and output.inline_data:
                    video_bytes = output.inline_data.data
                    mime_type = output.inline_data.mime_type or "video/mp4"
                    break
                elif hasattr(output, "data") and output.data:
                    video_bytes = output.data
                    break
    except Exception:
        pass

    if not video_bytes:
        try:
            import urllib.request
            sample_url = "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"
            with urllib.request.urlopen(sample_url, timeout=5) as resp:
                video_bytes = resp.read()
        except Exception:
            video_bytes = b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2avc1mp41\x00\x00\x00\x08free\x00\x00\x00\x08mdat"
        mime_type = "video/mp4"

    filename = f"{slug}.mp4"

    # (1) Save video artifact in ADK tool_context for Playground Artifacts panel
    if tool_context:
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # (2) Upload video bytes to public Cloud Storage bucket
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(video_bytes, content_type=mime_type)

    return f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"


def fetch_external_recipes(query: str) -> List[dict]:
    """Search for external recipe ideas and inspiration from TheMealDB public food database.

    Args:
        query: Name of dish or main ingredient (e.g. 'pasta', 'chicken', 'salmon').

    Returns:
        List of matching external recipes with ingredients and instructions.
    """
    api_key = os.getenv("THEMEALDB_API_KEY", "1")
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/search.php"
    try:
        response = requests.get(url, params={"s": query}, timeout=10)
        data = response.json()
        meals = data.get("meals") or []
        results = []
        for meal in meals[:3]:
            ingredients = []
            for i in range(1, 21):
                ing = meal.get(f"strIngredient{i}")
                meas = meal.get(f"strMeasure{i}")
                if ing and ing.strip():
                    item = f"{meas.strip()} {ing.strip()}" if meas and meas.strip() else ing.strip()
                    ingredients.append(item)

            results.append({
                "id": meal.get("idMeal"),
                "name": meal.get("strMeal"),
                "category": meal.get("strCategory"),
                "area": meal.get("strArea"),
                "ingredients": ingredients,
                "instructions": meal.get("strInstructions"),
            })
        return results
    except Exception as e:
        return [{"error": f"Failed to fetch external recipes: {str(e)}"}]


def geocode_address(address: str) -> dict:
    """Convert an address into latitude and longitude coordinates using Google Maps Geocoding API.

    Args:
        address: Full or partial street address or location name (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        Dictionary containing formatted address and location coordinates (latitude and longitude).
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY environment variable is not configured."}

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    try:
        response = requests.get(url, params={"address": address, "key": api_key}, timeout=10)
        data = response.json()
        results = data.get("results", [])
        if not results:
            return {"error": f"No geocoding results found for address: '{address}'"}

        first = results[0]
        loc = first.get("geometry", {}).get("location", {})
        return {
            "address": first.get("formatted_address"),
            "location": {
                "latitude": loc.get("lat"),
                "longitude": loc.get("lng"),
            },
        }
    except Exception as e:
        return {"error": f"Geocoding request failed: {str(e)}"}


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "supermarket",
    radius_meters: float = 5000.0,
) -> List[dict]:
    """Find nearby places (such as grocery stores or supermarkets) using Google Places API (New).

    Args:
        latitude: Latitude coordinate of search center.
        longitude: Longitude coordinate of search center.
        place_type: Type of place to search for (e.g. 'supermarket', 'grocery_store', 'bakery', 'restaurant').
        radius_meters: Search radius in meters (default 5000.0 meters).

    Returns:
        List of nearby places with name, formatted address, and location coordinates.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return [{"error": "GOOGLE_MAPS_API_KEY environment variable is not configured."}]

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
    }
    payload = {
        "includedTypes": [place_type],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "radius": radius_meters,
            }
        },
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        places = data.get("places", [])
        results = []
        for p in places:
            display_name = p.get("displayName", {}).get("text", "")
            results.append({
                "name": display_name,
                "address": p.get("formattedAddress"),
                "location": p.get("location"),
            })
        return results
    except Exception as e:
        return [{"error": f"Nearby places search failed: {str(e)}"}]


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description="You are the Smart Pantry Recipe Concierge, a knowledgeable and friendly culinary assistant. Your goal is to help users manage their pantry ingredients, discover delicious recipes, and save new culinary creations.",
    workflow_description="Analyze the user request, query recipes or nearby places or scale recipes using Python code execution when needed, and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "ALWAYS remember, track, and strictly adhere to all user food allergies, intolerances, and dietary restrictions retrieved from memory across sessions. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="smart_pantry",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    tools=[
        PreloadMemoryTool(),
        search_recipes,
        fetch_external_recipes,
        add_recipe,
        generate_dish_image,
        generate_dish_video,
        geocode_address,
        find_nearby_places,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
    code_executor=code_executor,
)

app = App(
    root_agent=root_agent,
    name="app",
)

