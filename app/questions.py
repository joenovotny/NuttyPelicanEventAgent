FIELDS_TO_QUESTIONS = {
    "start_date": "What are the event dates and public operating hours?",
    "expected_attendance": "What was the estimated attendance at the most recent event?",
    "vendor_fee": "What is the food-vendor fee?",
    "application_deadline": "What is the application deadline, and are food-vendor applications open?",
    "food_vendor_count": "How many food vendors do you expect?",
    "product_rules": "Are fresh cinnamon-glazed nuts and gourmet popcorn permitted, and are there exclusivity restrictions?",
    "power_details": "What electricity is available, at what amperage and cost, and what are the generator rules?",
    "permit_requirements": "What health-department or temporary-food permit requirements apply?",
    "insurance_requirements": "Is a certificate of insurance required?",
    "setup_details": "What are the booth size, setup, parking, vehicle-access, and overnight-security rules?",
    "cancellation_policy": "What is the rain, cancellation, and refund policy?",
    "application_url": "Could you share the official application link?",
}


def missing_questions(event):
    return [question for field, question in FIELDS_TO_QUESTIONS.items() if not getattr(event, field, None)]

