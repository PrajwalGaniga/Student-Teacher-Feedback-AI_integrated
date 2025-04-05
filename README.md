# EduTrack - Classroom Management Platform

![Classroom Management System](https://via.placeholder.com/150x50?text=EduTrack)  
*An interactive platform connecting teachers and students for seamless classroom management*

---

## 🌟 Key Features

### 👨‍🏫 Teacher Portal
| Feature | Description |
|---------|-------------|
| 🏫 Classroom Management | Create/manage classrooms with unique join codes |
| 📝 Quiz System | Build quizzes with multiple question types |
| ✅ Attendance Tracker | Record attendance with percentage calculations |
| 📊 Analytics Dashboard | View student progress reports |
| 📤 Excel Export | Download attendance data as spreadsheets |
| 💬 Feedback System | Receive and analyze student feedback |

### 👨‍🎓 Student Portal
| Feature | Description |
|---------|-------------|
| 🔍 Join Classrooms | Enter class codes to enroll |
| ✍️ Quiz Interface | Attempt quizzes with instant scoring |
| 📈 Progress Reports | View performance with AI-generated feedback |
| 📅 Attendance Portal | Check participation history |
| 🗣️ Feedback Submission | Rate and review teachers |

---

## 🚀 Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/project-code.git
cd project-code

2. Setup Virtual Environment

python -m venv venv

source venv/bin/activate

.\venv\Scripts\activate

3. Install Dependencies

pip install -r requirements.txt

4. Configure Environment

MONGODB_URI="mongodb+srv://yourdburi"
GEMINI_API_KEY="your-google-ai-key"
SECRET_KEY="your-secret-key-here"
DATABASE_NAME="school_db"

5. Run Application

uvicorn main:app --reload

🏗️ Project Structure

PROJECT-CODE/
├── __pycache__/
├── static/                      # Static assets
├── templates/                   # All HTML templates
│   ├── classrooms.html          # Classroom listing
│   ├── feedback_for.html        # Feedback selection
│   ├── feedback_form.html       # Feedback form
│   ├── firstpage.html           # Landing page
│   ├── index.html               # Main page
│   ├── join_classroom.html      # Classroom joining
│   ├── joined_classrooms.html   # Student's classes
│   ├── progress_report.html     # Student progress
│   ├── quiz_attempt.html        # Quiz interface
│   ├── quiz_display.html        # Quiz listing
│   ├── student_dashboard.html   # Student dashboard
│   ├── student_list.html        # Class roster
│   ├── student_login.html       # Student login
│   ├── student_profile.html     # Student profile
│   ├── student_register.html    # Student registration
│   ├── subject_list.html        # Subjects listing
│   ├── take_attendance.html     # Attendance taking
│   ├── teacher_classrooms.html  # Teacher's classes
│   ├── teacher_dashboard.html   # Teacher dashboard
│   ├── teacher_feedback.html    # Feedback review
│   ├── teacher_login.html       # Teacher login
│   ├── teacher_profile.html     # Teacher profile
│   ├── teacher_quiz.html        # Quiz creation
│   ├── teacher_register.html    # Teacher registration
│   ├── teacher_subjects.html    # Subject management
│   └── view_attendance.html     # Attendance viewing
├── .gitignore                  # Git ignore rules
├── main.py                     # Main application
├── README.md                   # This file
└── styles.css                  # Main stylesheet

✉️ Contact
Email: prajwalganiga06@gmail.com


