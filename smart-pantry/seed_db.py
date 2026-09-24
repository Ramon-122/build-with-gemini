import os
from google.cloud import firestore

# HARDCODED GCP Project ID (Do NOT use os.getenv("GOOGLE_CLOUD_PROJECT") or google.auth.default())
PROJECT_ID = "qwiklabs-gcp-02-075769363a76"


def seed_database():
    print(f"Connecting to Firestore for project: {PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)
    recipes_ref = db.collection("recipes")

    sample_recipes = [
        {
            "id": "mediterranean_chickpea_salad",
            "name": "Mediterranean Chickpea Salad",
            "ingredients": ["chickpeas", "cucumber", "cherry tomatoes", "feta cheese", "olive oil", "lemon juice", "red onion"],
            "instructions": "Combine rinsed chickpeas, diced cucumber, halved cherry tomatoes, and red onion. Toss with olive oil and lemon juice. Top with crumbled feta cheese.",
            "prep_time_minutes": 15,
            "cuisine": "Mediterranean",
            "dietary_tags": ["vegetarian", "gluten-free"]
        },
        {
            "id": "garlic_butter_salmon",
            "name": "Garlic Butter Pan-Seared Salmon",
            "ingredients": ["salmon fillets", "garlic", "butter", "lemon", "parsley", "salt", "black pepper"],
            "instructions": "Season salmon. Melt butter in a skillet over medium-high heat. Sear salmon 4 mins per side. Add minced garlic and lemon juice, spooning sauce over fish.",
            "prep_time_minutes": 20,
            "cuisine": "American",
            "dietary_tags": ["keto", "gluten-free", "pescatarian"]
        },
        {
            "id": "tofu_veggie_stir_fry",
            "name": "Crispy Tofu & Veggie Stir-Fry",
            "ingredients": ["firm tofu", "broccoli", "bell pepper", "soy sauce", "sesame oil", "ginger", "garlic", "rice"],
            "instructions": "Press and cube tofu, pan-fry until golden. Saute broccoli and bell peppers. Combine with ginger-soy sauce and serve over rice.",
            "prep_time_minutes": 25,
            "cuisine": "Asian",
            "dietary_tags": ["vegan", "vegetarian"]
        },
        {
            "id": "classic_avocado_toast",
            "name": "Avocado Toast with Everything Seasoning",
            "ingredients": ["sourdough bread", "ripe avocado", "lemon juice", "everything bagel seasoning", "red pepper flakes"],
            "instructions": "Toast sourdough bread. Mash avocado with lemon juice and salt. Spread on toast and sprinkle with everything bagel seasoning.",
            "prep_time_minutes": 10,
            "cuisine": "Contemporary",
            "dietary_tags": ["vegan", "vegetarian"]
        }
    ]

    for recipe in sample_recipes:
        doc_ref = recipes_ref.document(recipe["id"])
        doc_ref.set(recipe)
        print(f"Seeded recipe: {recipe['name']} ({recipe['id']})")

    print("Firestore database seeding completed successfully!")


if __name__ == "__main__":
    seed_database()
