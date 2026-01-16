import re

def parse_instruction(text: str):
    text = text.lower().strip()
    commands = []

    # ---------------- LOGIN ----------------
    if "login" in text:
        commands.append({
            "action": "navigate",
            "target": "login_page",
            "value": None
        })

        match = re.search(r"login with (\w+)", text)
        if match:
            commands.append({
                "action": "type",
                "target": "username_field",
                "value": match.group(1)
            })

        commands.append({
            "action": "click",
            "target": "submit_button",
            "value": None
        })

    # ---------------- FORM PAGE ----------------
    if "form" in text or "fill" in text:
        commands.append({
            "action": "navigate",
            "target": "form_page",
            "value": None
        })

        name = re.search(r"name as (\w+)", text)
        if name:
            commands.append({
                "action": "type",
                "target": "name_field",
                "value": name.group(1)
            })

        email = re.search(r"email as ([\w@.]+)", text)
        if email:
            commands.append({
                "action": "type",
                "target": "email_field",
                "value": email.group(1)
            })

        if "male" in text:
            commands.append({
                "action": "click",
                "target": "gender_male",
                "value": None
            })
        elif "female" in text:
            commands.append({
                "action": "click",
                "target": "gender_female",
                "value": None
            })

        if "student" in text:
            commands.append({
                "action": "type",
                "target": "role_select",
                "value": "student"
            })
        elif "developer" in text:
            commands.append({
                "action": "type",
                "target": "role_select",
                "value": "developer"
            })
        elif "tester" in text:
            commands.append({
                "action": "type",
                "target": "role_select",
                "value": "tester"
            })

    # ---------------- SUBMIT ----------------
    if "submit" in text:
        commands.append({
            "action": "click",
            "target": "submit_button",
            "value": None
        })

    return commands
