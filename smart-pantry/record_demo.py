import os
import time
import shutil
from playwright.sync_api import sync_playwright

def record_demo():
    url = "https://smart-pantry-frontend-796386059624.us-east1.run.app"
    artifacts_dir = "/config/.gemini/antigravity/brain/af9d739b-f2ec-4c10-bd8c-79491f125bfa"
    os.makedirs(artifacts_dir, exist_ok=True)
    video_dir = "/tmp/demo_recordings"
    os.makedirs(video_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=video_dir,
            record_video_size={"width": 1280, "height": 800}
        )
        page = context.new_page()
        print("Navigating to frontend UI...")
        page.goto(url, wait_until="networkidle")
        time.sleep(2)

        # Prompt 1
        prompt1 = "Hi! I have pasta, garlic, olive oil, and parmesan. What delicious meal can I make for dinner?"
        print("Sending Prompt 1...")
        input_box = page.locator("#input")
        input_box.fill(prompt1)
        time.sleep(1)
        
        send_btn = page.locator("#form button")
        send_btn.click()
            
        print("Waiting for response to Prompt 1...")
        time.sleep(12)

        # Prompt 2
        prompt2 = "Can you search for a gourmet Garlic Pesto Pasta recipe, save it to my collection, compute its macros with python, and generate a photo of the dish?"
        print("Sending Prompt 2...")
        input_box.fill(prompt2)
        time.sleep(1)
        send_btn.click()

        print("Waiting for response and tool executions for Prompt 2...")
        time.sleep(25)

        # Take screenshot of final UI state
        page.screenshot(path=os.path.join(artifacts_dir, "demo_screenshot.png"))

        video_path = page.video.path()
        context.close()
        browser.close()

        target_video = os.path.join(artifacts_dir, "agent_demo.webm")
        shutil.copy(video_path, target_video)
        print(f"Recorded video saved to {target_video}")

if __name__ == "__main__":
    record_demo()
