import os
import sqlite3
import json
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate

def connect_to_db():
    con = sqlite3.connect("doctors.db")
    cur = con.cursor()
    cur.execute('''CREATE TABLE if not exists bookings(
            doctor TEXT NOT NULL,
            doctor_id INTEGER PRIMARY KEY,
            time DATETIME NOT NULL, 
            date DATE NOT NULL, 
            status BOOLEAN NOT NULL,
            patient_name TEXT NOT NULL
            )''')

    sample_data = [
        ('Dr. Sarah Johnson', 1001, '09:00:00', '2025-08-26', False, 'John Doe'),
        ('Dr. Michael Chen', 1002, '10:00:00', '2025-08-25', False, 'Jane Smith'),
        ('Dr. Emily Brown', 1003, '14:00:00', '2025-08-23', False, 'Robert Wilson'),
        ('Dr. David Lee', 1004, '11:00:00', '2025-08-24', False, 'Maria Garcia')
    ]
    for booking in sample_data:
        cur.execute('''INSERT OR IGNORE INTO bookings 
                    (doctor, doctor_id, time, date, status, patient_name)
                    VALUES (?, ?, ?, ?, ?, ?)''', booking)
    con.commit()
    return con

def query_doctor_slots(doctor_name=None, date=None, limit=10):
    con = sqlite3.connect("doctors.db")
    cur = con.cursor()

    sql = "SELECT doctor, date, time FROM bookings WHERE status = 0"
    params = []
    if doctor_name:
        sql += " AND doctor LIKE ?"
        params.append(f"%{doctor_name}%")
    if date:
        sql += " AND date = ?"
        params.append(date)
    sql += " ORDER BY date, time LIMIT ?"
    params.append(limit)

    cur.execute(sql, params)
    rows = cur.fetchall()
    con.close()

    slots = [{"doctor": d, "date": dt, "time": t} for d, dt, t in rows]
    return slots

def book_appointment(patient, doctor, date, time):
    conn = sqlite3.connect("doctors.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE bookings
        SET status = 1, patient_name = ?
        WHERE doctor = ? AND date = ? AND time = ?
    """, (patient, doctor, date, time))
    conn.commit()
    conn.close()

load_dotenv()
google_api_key = os.environ.get("GOOGLE_API_KEY")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=google_api_key,
    temperature=0.7,
    convert_system_message_to_human=True
)

prompt_template = ChatPromptTemplate.from_template(
    "You are a helpful healthcare assistant. Today's date is {today}.\n"
    "The following doctor slots are available (JSON):\n{doctor_slots}\n"
    "⚠️ Only accept doctor names and slots from this list.\n"
    "Conversation so far:\n{history}\n"
    "User: {user_input}"
)

def main():
    st.title("🏥 Healthcare Appointment Chatbot")
    connect_to_db()

    if "history" not in st.session_state:
        st.session_state.history = ""

    user_input = st.chat_input("Type your message...")
    if user_input:
        # Step 1: detect doctor name or date (simple heuristic, could use regex/NLP)
        doctor_hint = None
        date_hint = None
        for word in user_input.split():
            if word.lower().startswith("dr."):
                doctor_hint = word
            try:
                dt = datetime.strptime(word, "%Y-%m-%d")
                date_hint = dt.strftime("%Y-%m-%d")
            except:
                pass

        # Step 2: query relevant slots
        slots = query_doctor_slots(doctor_hint, date_hint, limit=10)
        slots_json = json.dumps(slots, indent=2) if slots else "[]"

        # Step 3: build prompt
        system_prompt = prompt_template.format(
            today=datetime.now().strftime("%Y-%m-%d"),
            doctor_slots=slots_json,
            history=st.session_state.history,
            user_input=user_input
        )

        # Step 4: get response
        response = llm.invoke(system_prompt)
        assistant_reply = response.content

        # Display
        st.chat_message("user").write(user_input)
        st.chat_message("assistant").write(assistant_reply)

        # Update history
        st.session_state.history += f"\nUser: {user_input}\nAssistant: {assistant_reply}"

        # Step 5: Optional booking confirmation
        if "book" in assistant_reply.lower() and slots:
            for slot in slots:
                if slot["doctor"] in assistant_reply and slot["date"] in assistant_reply and slot["time"] in assistant_reply:
                    if st.button(f"Confirm booking: {slot['doctor']} on {slot['date']} at {slot['time']}"):
                        patient_name = "User"  # could be asked separately
                        book_appointment(patient_name, slot["doctor"], slot["date"], slot["time"])
                        st.success(f"Appointment booked for {patient_name} with {slot['doctor']} on {slot['date']} at {slot['time']}.")

if __name__ == "__main__":
    main()
