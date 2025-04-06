from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pymongo import MongoClient
from bson import ObjectId
import secrets, uuid, random, string
import google.generativeai as genai
from datetime import datetime
from passlib.context import CryptContext
from openpyxl import Workbook
from io import BytesIO
from dotenv import load_dotenv
from pymongo.errors import PyMongoError
import os
import certifi
import ssl
print(ssl.OPENSSL_VERSION)


load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-pro-latest') 

app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SECRET_KEY", secrets.token_hex(32))
)
context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
context.verify_mode = ssl.CERT_REQUIRED
context.check_hostname = True

mongo_client = MongoClient(
    "mongodb+srv://school_db:prajwal%402005@cluster0.6qmnao2.mongodb.net/school_db?retryWrites=true&w=majority",
    connectTimeoutMS=30000,
    socketTimeoutMS=30000
)

@app.get("/db-check")
async def db_check():
    try:
        db.command('ping')
        return {"status": "success", "collections": db.list_collection_names()}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
# Access database
db = mongo_client.school_db

# Access collections
classrooms_collection = db.classrooms
quizzes_collection = db.quizzes
students_collection = db.students
students_users = db.student_user  # Note: consider renaming to student_users for consistency
results_collection = db.results
teachers_collection = db.teachers

templates = Jinja2Templates(directory="templates")
@app.get("/db-health")
async def healthcheck():
    try:
        db.command('ping')
        return {"status": "healthy", "collections": db.list_collection_names()}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error", "detail": str(exc)}
    )

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("firstpage.html", {"request": request})

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def generate_student_id():
    return "STU" + str(uuid.uuid4().int)[:6]

@app.get("/student-login")
async def student_login_page(request: Request):
    return templates.TemplateResponse("student_login.html", {"request": request})

@app.get("/student-register")
async def student_register_page(request: Request):
    return templates.TemplateResponse("student_register.html", {"request": request})

@app.post("/student-register")
async def student_register(request: Request):
    try:
        # Get form data
        form_data = await request.form()
        name = form_data.get("name")
        email = form_data.get("email")
        password = form_data.get("password")
        level = form_data.get("level")

        # Validate required fields
        if not all([name, email, password, level]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All fields are required"
            )

        # Check if email exists
        if students_collection.find_one({"email": email}):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Hash password
        hashed_password = pwd_context.hash(password)

        # Create student document
        student_data = {
            "student_id": generate_student_id(),
            "name": name,
            "email": email,
            "password": hashed_password,
            "level": level,
            "created_at": datetime.now()
        }

        # Insert document with error handling
        result = students_collection.insert_one(student_data)
        if not result.inserted_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create student account"
            )

        return RedirectResponse(
            url="/student-login",
            status_code=status.HTTP_303_SEE_OTHER
        )

    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )

@app.post("/student-login")
async def student_login(request: Request):
    form_data = await request.form()
    email = form_data.get("email")
    password = form_data.get("password")

    student = students_collection.find_one({"email": email})
    
    if not student or not pwd_context.verify(password, student["password"]):
        error_message = "Invalid email or password"
        return templates.TemplateResponse(
            "student_login.html",
            {
                "request": request,
                "error_message": error_message
            }
        )

    request.session["student_id"] = student["student_id"]

    return RedirectResponse(url="/student-dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/student-dashboard", response_class=HTMLResponse)
async def student_dashboard(request: Request):
    student_id = request.session.get("student_id")
    if not student_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    student = students_collection.find_one({"student_id": student_id})
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    return templates.TemplateResponse(
        "student_dashboard.html",
        {"request": request, "student": student}
    )

@app.post("/verify-student-id")
async def verify_student_id(request: Request):
    data = await request.json()
    student_id = data.get("student_id")

    if not student_id:
        raise HTTPException(status_code=400, detail="Student ID is required.")

    student = students_collection.find_one({"student_id": student_id})

    if student:
        return {"exists": True}
    else:
        return {"exists": False}

@app.get("/student-profile/{student_id}", response_class=HTMLResponse)
async def student_profile(request: Request):
    student_id = request.session.get("student_id")
    if not student_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    student = students_collection.find_one({"student_id": student_id})
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    if "progress" not in student:
        student["progress"] = {
            "quizzes_attempted": 0,
            "average_score": 0
        }

    return templates.TemplateResponse(
        "student_profile.html",
        {"request": request, "student": student}
    )

@app.post("/student-profile/{student_id}/update")
async def update_profile(request: Request):
    student_id = request.session.get("student_id")
    if not student_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    form_data = await request.form()

    name = form_data.get("name")
    level = form_data.get("level")
    father_name = form_data.get("father_name")
    mother_name = form_data.get("mother_name")
    phone_number = form_data.get("phone_number")
    address = form_data.get("address")

    students_collection.update_one(
        {"student_id": student_id},
        {"$set": {
            "name": name,
            "level": level,
            "father_name": father_name,
            "mother_name": mother_name,
            "phone_number": phone_number,
            "address": address
        }}
    )

    return JSONResponse(content={"message": "Profile updated successfully"})

@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return JSONResponse(content={"message": "Logged out successfully"})

@app.get("/teacher-register", response_class=HTMLResponse)
async def teacher_register_page(request: Request):
    return templates.TemplateResponse("teacher_register.html", {"request": request})

@app.get("/teacher-login", response_class=HTMLResponse)
async def teacher_login_page(request: Request):
    return templates.TemplateResponse("teacher_login.html", {"request": request})

@app.post("/teacher-register")
async def teacher_register(request: Request):
    form_data = await request.form()
    name = form_data.get("name")
    email = form_data.get("email")
    password = form_data.get("password")

    if teachers_collection.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    teacher_id = f"TCH{secrets.token_hex(3).upper()}"

    teachers_collection.insert_one({
        "teacher_id": teacher_id,
        "name": name,
        "email": email,
        "password": password, 
        "progress": {
            "quizzes_created": 0,
            "average_rating": 0
        }
    })

    return RedirectResponse(url="/teacher-login", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/teacher-login")
async def teacher_login(request: Request):
    form_data = await request.form()
    email = form_data.get("email")
    password = form_data.get("password")

    teacher = teachers_collection.find_one({"email": email})
    
    if not teacher or teacher["password"] != password:  
        error_message = "Invalid email or password"
        return templates.TemplateResponse(
            "teacher_login.html",  
            {
                "request": request,
                "error_message": error_message
            }
        )

    request.session["teacher_id"] = teacher["teacher_id"]

    return RedirectResponse(url="/teacher-dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/teacher-dashboard", response_class=HTMLResponse)
async def teacher_dashboard(request: Request):
    teacher_id = request.session.get("teacher_id")
    if not teacher_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    teacher = teachers_collection.find_one({"teacher_id": teacher_id})
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")

    if "progress" not in teacher:
        teacher["progress"] = {
            "quizzes_created": 0,
            "average_rating": 0
        }

    return templates.TemplateResponse(
        "teacher_dashboard.html",
        {"request": request, "teacher": teacher}
    )

@app.get("/teacher-profile/{teacher_id}", response_class=HTMLResponse)
async def teacher_profile(request: Request):
    teacher_id = request.session.get("teacher_id")
    if not teacher_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    teacher = teachers_collection.find_one({"teacher_id": teacher_id})
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")

    if "progress" not in teacher:
        teacher["progress"] = {
            "quizzes_created": 0,
            "average_rating": 0
        }
    return templates.TemplateResponse(
        "teacher_profile.html",
        {"request": request, "teacher": teacher}
    )

@app.post("/teacher-profile/{teacher_id}/update")
async def update_teacher_profile(request: Request):
    teacher_id = request.session.get("teacher_id")
    if not teacher_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    form_data = await request.form()
    name = form_data.get("name")
    email = form_data.get("email")
    password = form_data.get("password") 
    degree = form_data.get("degree")
    specialization = form_data.get("specialization")
    university = form_data.get("university")
    subjects_taught = form_data.get("subjects_taught")
    skills = form_data.get("skills")

    teachers_collection.update_one(
        {"teacher_id": teacher_id},
        {"$set": {
            "name": name,
            "email": email,
            "password": password,
            "degree": degree,
            "specialization": specialization,
            "university": university,
            "subjects_taught": subjects_taught,
            "skills": skills
        }}
    )

    return JSONResponse(content={"message": "Profile updated successfully"})

@app.get("/teacher-classrooms")
async def teacher_classrooms(request: Request):
    try:
        classrooms = list(classrooms_collection.find({}, {"_id": 1, "name": 1, "c_code": 1}))
        for classroom in classrooms:
            classroom["_id"] = str(classroom["_id"])
        return templates.TemplateResponse("teacher_classrooms.html", {"request": request, "classrooms": classrooms})
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch classrooms")

def generate_unique_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@app.post("/create-class")
async def create_classroom(name: str = Form(...), teacher_id: str = Form(...)):
    if not name or len(name) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid classroom name"
        )

    teacher = teachers_collection.find_one({"teacher_id": teacher_id})
    if not teacher:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "Teacher ID not found"}
        )

    c_code = generate_unique_code()

    new_classroom = {
        "name": name,
        "c_code": c_code,
        "teacher_id": teacher_id
    }

    try:
        classroom_insert_result = classrooms_collection.insert_one(new_classroom)
        classroom_id = classroom_insert_result.inserted_id
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create classroom"
        )

    try:
        teachers_collection.update_one(
            {"teacher_id": teacher_id},
            {"$push": {"classrooms_created": {"classroom_id": classroom_id, "classroom_name": name,"c_code":c_code}}},
            upsert=True
        )
    except Exception as e:
        classrooms_collection.delete_one({"_id": classroom_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update teacher's classrooms_created field"
        )

    return RedirectResponse(url="/teacher-classrooms", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/edit-class/{class_id}")
async def edit_classroom(request: Request, class_id: str, name: str = Form(...)):
    try:
        teacher_id = request.session.get("teacher_id")
        if not teacher_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        classroom_id = ObjectId(class_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid classroom ID"
        )

    result = classrooms_collection.update_one(
        {"_id": classroom_id},
        {"$set": {"classroom_name": name}}
    )

    teacher_update = teachers_collection.update_one(
        {"teacher_id": teacher_id, "classrooms_created.classroom_id": classroom_id},
        {"$set": {"classrooms_created.$.classroom_name": name}}
    )

    if result.matched_count == 0 or teacher_update.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Classroom not found"
        )

    return RedirectResponse(url="/teacher-classrooms-manage", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/delete-class/{class_id}")
async def delete_classroom(request: Request, class_id: str):
    try:
        teacher_id = request.session.get("teacher_id")
        if not teacher_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        classroom_id = ObjectId(class_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid classroom ID"
        )

    classroom_delete = classrooms_collection.delete_one({"_id": classroom_id})

    teacher_update = teachers_collection.update_one(
        {"teacher_id": teacher_id},
        {"$pull": {"classrooms_created": {"classroom_id": classroom_id}}}
    )

    if classroom_delete.deleted_count == 0 or teacher_update.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Classroom not found"
        )

    return RedirectResponse(url="/teacher-classrooms-manage", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/teacher-classrooms-manage")
async def teacher_classrooms(request: Request):
    try:
        teacher_id = request.session.get("teacher_id")
        if not teacher_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        teacher = teachers_collection.find_one({"teacher_id": teacher_id})
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher not found")

        classrooms_created = teacher.get("classrooms_created", [])

        classrooms = []
        for classroom in classrooms_created:
            classrooms.append({
                "name": classroom.get("classroom_name"),
                "c_code": classroom.get("c_code"),
                "_id": str(classroom.get("classroom_id"))
            })

        teacher_name = request.session.get("teacher_name")
        return templates.TemplateResponse("teacher_subjects.html", {
            "request": request,
            "classrooms": classrooms,
            "teacher_name": teacher_name
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch classrooms")

@app.post("/edit-classroom/{class_id}")
async def edit_classroom(class_id: str, name: str = Form(...)):
    classrooms_collection.update_one({"_id": ObjectId(class_id)}, {"$set": {"name": name}})
    teachers_collection.update_one({})
    return RedirectResponse(url="/teacher-classrooms-manage", status_code=303)

@app.get("/create-quiz")
async def create_quiz_page(request: Request):
    return templates.TemplateResponse("teacher_quiz.html", {"request": request})

@app.post("/create-quiz")
async def create_quiz(request: Request):
    data = await request.json()

    quiz_data = {
        "title": data["title"],
        "description": data["description"],
        "level": data["level"],
        "for": data["for"],
        "questions": data["questions"]
    }

    quizzes_collection.insert_one(quiz_data)

    return {"message": "Quiz created successfully!"}

@app.get("/join-classroom", response_class=HTMLResponse)
async def join_classroom_page(request: Request):
    return templates.TemplateResponse("join_classroom.html", {"request": request})

@app.post("/join-classroom")
async def join_classroom(request: Request, class_code: str = Form(...), student_id: str = Form(...)):
    student = students_collection.find_one({"student_id": student_id})
    if not student:
        return RedirectResponse(url="/student-register", status_code=status.HTTP_303_SEE_OTHER)

    classroom = classrooms_collection.find_one({"c_code": class_code})
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found. Please check the code and try again.")

    if class_code in [c["c_code"] for c in student.get("classrooms_joined", [])]:
        raise HTTPException(status_code=400, detail="You have already joined this classroom.")

    classroom_name = classroom.get("name")

    students_collection.update_one(
        {"student_id": student_id},
        {"$push": {"classrooms_joined": {"c_code": class_code, "name": classroom_name}}}
    )

    return RedirectResponse(url="/student-dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/submit-quiz")
async def submit_quiz(request: Request):
    data = await request.json()
    
    quiz = quizzes_collection.find_one({"_id": ObjectId(data["quiz_id"])})
    
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    result_data = {
        "student_id": data["student_id"],
        "quiz_id": data["quiz_id"],
        "quiz_title": quiz.get("title"),
        "submitted_at": datetime.now(),
        "total_questions": len(quiz["questions"]),
        "correct_answers": data["correct_answers"],
        "score_percentage": (data["correct_answers"] / len(quiz["questions"])) * 100,
        "answers": []
    }
    
    for answer in data["answers"]:
        result_data["answers"].append({
            "question": answer["question"],
            "selected_option": answer["selected_option"],
            "correct_option": answer["correct_option"],
            "is_correct": answer["selected_option"] == answer["correct_option"]
        })
    
    results_collection.insert_one(result_data)
    return {"message": "Quiz submitted successfully!", "score": result_data["score_percentage"]}

@app.get("/quiz-attempt/{quiz_id}")
async def quiz_attempt(request: Request, quiz_id: str):
    try:
        quiz = quizzes_collection.find_one({"_id": ObjectId(quiz_id)})
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        quiz["_id"] = str(quiz["_id"])
        
        for question in quiz["questions"]:
            question["correctOption"] = question["correctOption"]
            question["correct_answer_text"] = question["options"][question["correctOption"]]
        
        return templates.TemplateResponse("quiz_attempt.html", {
            "request": request,
            "quiz": quiz
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/quizzes")
async def display_quizzes(request: Request, level: str = None, profession: str = None):
    try:
        query = {}
        if level:
            query["level"] = level
        if profession:
            query["for"] = profession

        quizzes = list(quizzes_collection.find(query, {"_id": 1, "title": 1, "description": 1, "level": 1, "for": 1}))
        for quiz in quizzes:
            quiz["_id"] = str(quiz["_id"])

        return templates.TemplateResponse("quiz_display.html", {"request": request, "quizzes": quizzes})
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch quizzes")

@app.get("/classrooms")
async def get_classrooms(request: Request):
    teacher_id = request.session.get("teacher_id")
    
    if not teacher_id:
        return RedirectResponse(url="/login")
    
    teacher = teachers_collection.find_one({"teacher_id": teacher_id})
    
    if not teacher:
        return RedirectResponse(url="/login")
    
    classroom_ids = [classroom["classroom_id"] for classroom in teacher.get("classrooms_created", [])]
    
    classrooms = list(classrooms_collection.find(
        {"_id": {"$in": classroom_ids}},
        {"_id": 0, "name": 1, "c_code": 1}
    ))
    
    return templates.TemplateResponse("classrooms.html", {"request": request, "classrooms": classrooms})

@app.get("/students/{classroom_code}")
async def get_students(request: Request, classroom_code: str):
    students = list(students_collection.find(
        {"classrooms_joined.c_code": classroom_code},
        {"_id": 0, "name": 1, "student_id": 1, "email": 1}
    ).sort("name", 1))

    classroom = classrooms_collection.find_one(
        {"c_code": classroom_code},
        {"_id": 0, "name": 1}
    )
    classroom_name = classroom["name"] if classroom else "Unknown Classroom"
    
    return templates.TemplateResponse(
        "student_list.html",
        {
            "request": request,
            "students": students,
            "classroom_code": classroom_code,
            "classroom_name": classroom_name
        }
    )

@app.get("/student-joined-classes")
async def student_dashboard(request: Request):
    student_id = request.session.get("student_id") 
    print(student_id)
    if not student_id:
        return {"error": "User not logged in"}

    student = students_collection.find_one({"student_id": student_id})
    if not student:
        return {"error": "Student not found"}

    joined_classes = student.get("classrooms_joined", [])

    return templates.TemplateResponse("joined_classrooms.html", {
        "request": request,
        "joined_classes": joined_classes
    })

def generate_feedback(question, selected_option, correct_option):
    if selected_option == correct_option:
        return "Correct! Good job!"
    
    prompt = f"""
    As an educational tutor, provide constructive feedback on this quiz answer:
    
    Question: {question}
    Student's Answer: {selected_option}
    Correct Answer: {correct_option}
    
    Please:
    1. Explain why the student's answer is incorrect
    2. Explain why the correct answer is right
    3. Provide 1-2 specific improvement tips
    4. Keep the response under 100 words
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Could not generate feedback: {str(e)}"

@app.get("/student_report", response_class=HTMLResponse)
async def student_report(request: Request):
    student_id = request.session.get("student_id")
    if not student_id:
        return {"error": "Student ID not found in session. Please log in."}

    student_results = list(results_collection.find({"student_id": student_id}).sort("submitted_at", 1))
    
    report = []
    total_questions = 0
    total_correct = 0
    subject_stats = {}
    
    progress_data = {
        'dates': [],
        'daily_scores': [],
        'quiz_titles': [],
        'periods': [],
        'scores': [],
        'trend': [],
        'quizzes': []
    }
    
    current_week = None
    weekly_scores = []
    weekly_quizzes = []

    for result in student_results:
        quiz_title = result.get("quiz_title", "Unknown Quiz")
        subject = result.get("subject", "General")
        score_percentage = result.get("score_percentage", 0)
        quiz_total_questions = result.get("total_questions", 0)
        quiz_correct_answers = result.get("correct_answers", 0)
        submitted_at = result.get("submitted_at")
        
        total_questions += quiz_total_questions
        total_correct += quiz_correct_answers
        
        if subject not in subject_stats:
            subject_stats[subject] = {
                'total_questions': 0,
                'total_correct': 0
            }
        subject_stats[subject]['total_questions'] += quiz_total_questions
        subject_stats[subject]['total_correct'] += quiz_correct_answers
        
        if submitted_at:
            progress_data['dates'].append(submitted_at.strftime("%Y-%m-%d"))
            progress_data['daily_scores'].append(score_percentage)
            progress_data['quiz_titles'].append(quiz_title)
            
            week_key = f"{submitted_at.strftime('%b')} Week {submitted_at.isocalendar()[1]}"
            
            if week_key != current_week:
                if current_week and weekly_scores:
                    avg_score = sum(weekly_scores)/len(weekly_scores)
                    progress_data['periods'].append(current_week)
                    progress_data['scores'].append(avg_score)
                    progress_data['quizzes'].append(len(weekly_scores))
                    
                    if len(progress_data['scores']) > 1:
                        trend = 1 if avg_score > progress_data['scores'][-2] else (-1 if avg_score < progress_data['scores'][-2] else 0)
                        progress_data['trend'].append(trend)
                    else:
                        progress_data['trend'].append(0)
                
                current_week = week_key
                weekly_scores = []
            
            weekly_scores.append(score_percentage)
        
        feedback_list = []
        for answer in result.get("answers", []):
            if not answer.get("is_correct", False):
                feedback = generate_feedback(
                    answer.get("question", ""),
                    answer.get("selected_option", ""),
                    answer.get("correct_option", "")
                )
                feedback_list.append({
                    "question": answer.get("question", ""),
                    "feedback": feedback
                })

        report.append({
            "quiz_title": quiz_title,
            "subject": subject,
            "score_percentage": score_percentage,
            "total_questions": quiz_total_questions,
            "correct_answers": quiz_correct_answers,
            "submitted_at": submitted_at.strftime("%Y-%m-%d %H:%M") if submitted_at else "N/A",
            "feedback": feedback_list
        })
    
    if current_week and weekly_scores:
        avg_score = sum(weekly_scores)/len(weekly_scores)
        progress_data['periods'].append(current_week)
        progress_data['scores'].append(avg_score)
        progress_data['quizzes'].append(len(weekly_scores))
        if len(progress_data['scores']) > 1:
            trend = 1 if avg_score > progress_data['scores'][-2] else (-1 if avg_score < progress_data['scores'][-2] else 0)
            progress_data['trend'].append(trend)
        else:
            progress_data['trend'].append(0)
    
    overall_score = round((total_correct / total_questions) * 100, 2) if total_questions > 0 else 0
    
    for subject, stats in subject_stats.items():
        stats['percentage'] = round((stats['total_correct'] / stats['total_questions']) * 100, 2) if stats['total_questions'] > 0 else 0

    return templates.TemplateResponse(
        "progress_report.html",
        {
            "request": request,
            "report": report,
            "total_questions": total_questions,
            "total_correct": total_correct,
            "overall_score": overall_score,
            "subject_stats": subject_stats,
            "progress_data": progress_data
        }
    )

@app.post("/set-student-session")
async def set_student_session(request: Request):
    form_data = await request.form()
    student_id = form_data.get("student_id")
    if student_id:
        request.session["student_id"] = student_id
    return RedirectResponse(url="/student_report", status_code=303)

@app.get("/classrooms-for-attendance")
async def get_classrooms(request: Request):
    teacher_id = request.session.get("teacher_id")
    
    if not teacher_id:
        return RedirectResponse(url="/login")
    
    teacher = teachers_collection.find_one({"teacher_id": teacher_id})
    
    if not teacher:
        return RedirectResponse(url="/login")
    
    classroom_ids = [classroom["classroom_id"] for classroom in teacher.get("classrooms_created", [])]
    
    classrooms = list(classrooms_collection.find(
        {"_id": {"$in": classroom_ids}},
        {"_id": 0, "name": 1, "c_code": 1}
    ))
    
    return templates.TemplateResponse("classrooms_for attendance.html", {"request": request, "classrooms": classrooms})

@app.get("/take-attendance/{classroom_code}", response_class=HTMLResponse)
async def take_attendance_page(request: Request, classroom_code: str):
    classroom = db.classrooms.find_one({"c_code": classroom_code})
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")
    
    students = list(db.students.find({
        "classrooms_joined.c_code": classroom_code
    }).sort("name", 1))
    
    for student in students:
        student["_id"] = str(student["_id"])
    
    return templates.TemplateResponse("take_attendance.html", {
        "request": request,
        "classroom": classroom,
        "students": students,
        "current_date": datetime.now().strftime("%Y-%m-%d")
    })

@app.post("/api/attendance/{classroom_code}/record")
async def record_attendance(classroom_code: str, request: Request):
    try:
        data = await request.json()
        date = data.get("date")
        records = data.get("records", [])
        
        if not date or not records:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        classroom = db.classrooms.find_one({"c_code": classroom_code})
        if not classroom:
            raise HTTPException(status_code=404, detail="Classroom not found")
        
        total_classes = db.attendance.count_documents({"classroom_code": classroom_code}) + 1
        
        attendance_records = []
        for record in records:
            student_id = record.get("student_id")
            is_present = record.get("present", False)
            
            student = db.students.find_one({"student_id": student_id})
            if not student:
                continue
                
            attendance_records.append({
                "student_id": student_id,
                "student_name": student.get("name"),
                "present": is_present
            })
            
            attendance_record = next(
                (item for item in student.get("attendance", []) 
                if item.get("classroom_code") == classroom_code),
                None
            )
            
            if attendance_record:
                new_present = attendance_record.get("present_classes", 0) + (1 if is_present else 0)
                new_total = total_classes
                new_percentage = round((new_present / new_total) * 100, 2) if new_total > 0 else 0
                
                db.students.update_one(
                    {
                        "student_id": student_id,
                        "attendance.classroom_code": classroom_code
                    },
                    {
                        "$set": {
                            "attendance.$.present_classes": new_present,
                            "attendance.$.total_classes": new_total,
                            "attendance.$.percentage": new_percentage
                        },
                        "$push": {
                            "attendance.$.history": {
                                "date": date,
                                "present": is_present
                            }
                        }
                    }
                )
            else:
                new_attendance = {
                    "classroom_code": classroom_code,
                    "classroom_name": classroom.get("name"),
                    "present_classes": 1 if is_present else 0,
                    "total_classes": 1,
                    "percentage": 100 if is_present else 0,
                    "history": [{
                        "date": date,
                        "present": is_present
                    }]
                }
                
                db.students.update_one(
                    {"student_id": student_id},
                    {"$push": {"attendance": new_attendance}},
                    upsert=True
                )
        
        attendance_data = {
            "classroom_code": classroom_code,
            "classroom_name": classroom.get("name"),
            "date": date,
            "records": attendance_records,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        db.attendance.insert_one(attendance_data)
        
        return JSONResponse({
            "success": True,
            "message": "Attendance recorded permanently"
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def update_student_attendance(student_id: str, classroom_code: str, classroom_name: str, date: str, present: bool):
    try:
        update_query = {
            "$inc": {
                "attendance.$[elem].total_classes": 1,
                "attendance.$[elem].present_classes": 1 if present else 0
            },
            "$push": {
                "attendance.$[elem].history": {
                    "date": date,
                    "present": present
                }
            },
            "$setOnInsert": {
                "attendance.$[elem].classroom_name": classroom_name,
                "attendance.$[elem].percentage": 0
            }
        }
        
        if present:
            update_query["$inc"]["attendance.$[elem].present_classes"] = 1
        
        result = db.students.update_one(
            {
                "student_id": student_id,
                "attendance.classroom_code": classroom_code
            },
            update_query,
            array_filters=[{"elem.classroom_code": classroom_code}],
            upsert=True
        )
        
        if result.matched_count == 0:
            new_attendance = {
                "classroom_code": classroom_code,
                "classroom_name": classroom_name,
                "present_classes": 1 if present else 0,
                "total_classes": 1,
                "percentage": 100 if present else 0,
                "history": [{
                    "date": date,
                    "present": present
                }]
            }
            
            db.students.update_one(
                {"student_id": student_id},
                {"$push": {"attendance": new_attendance}},
                upsert=True
            )
        
        student = db.students.find_one({"student_id": student_id})
        if student:
            for subject in student.get("attendance", []):
                if subject["classroom_code"] == classroom_code and subject["total_classes"] > 0:
                    percentage = round((subject["present_classes"] / subject["total_classes"]) * 100, 2)
                    db.students.update_one(
                        {
                            "student_id": student_id,
                            "attendance.classroom_code": classroom_code
                        },
                        {"$set": {"attendance.$.percentage": percentage}}
                    )
    
    except Exception as e:
        print(f"Error updating student {student_id}: {str(e)}")
        
@app.get("/view-attendance/{classroom_code}", response_class=HTMLResponse)
async def view_attendance_page(
    request: Request, 
    classroom_code: str,
    search: str = Query(None, description="Search student by name or ID")
):
    classroom = db.classrooms.find_one({"c_code": classroom_code})
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")
    
    total_classes = db.attendance.count_documents({"classroom_code": classroom_code})
    query = {"classrooms_joined.c_code": classroom_code}
    
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"student_id": {"$regex": search, "$options": "i"}}
        ]
    
    students = list(db.students.find(query).sort("name", 1))
    student_data = []
    
    for student in students:
        attendance_record = next(
            (item for item in student.get("attendance", []) 
             if item.get("classroom_code") == classroom_code),
            None
        )
        
        present_classes = attendance_record.get("present_classes", 0) if attendance_record else 0
        percentage = attendance_record.get("percentage", 0) if attendance_record else 0
        
        student_data.append({
            "id": str(student["_id"]),
            "student_id": student["student_id"],
            "name": student["name"],
            "present_classes": present_classes,
            "percentage": percentage,
            "total_classes": total_classes
        })
    
    if student_data and total_classes > 0:
        total_present = sum(s["present_classes"] for s in student_data)
        overall_percentage = round((total_present / (len(student_data) * total_classes)) * 100)
    else:
        overall_percentage = 0
    
    return templates.TemplateResponse("view_attendance.html", {
        "request": request,
        "classroom": classroom,
        "students": student_data,
        "total_classes": total_classes,
        "overall_percentage": overall_percentage,
        "search_query": search or ""
    })

@app.post("/api/attendance/{classroom_code}/update")
async def update_attendance(classroom_code: str, request: Request):
    try:
        data = await request.json()
        student_id = data.get("student_id")
        present_classes = int(data.get("present_classes", 0))
        
        if not student_id:
            raise HTTPException(status_code=400, detail="Missing student_id")
        
        total_classes = db.attendance.count_documents({"classroom_code": classroom_code})
        if present_classes > total_classes:
            raise HTTPException(status_code=400, detail="Present classes cannot exceed total classes")
        
        percentage = round((present_classes / total_classes) * 100, 2) if total_classes > 0 else 0
        
        result = db.students.update_one(
            {"student_id": student_id, "attendance.classroom_code": classroom_code},
            {"$set": {
                "attendance.$.present_classes": present_classes,
                "attendance.$.total_classes": total_classes,
                "attendance.$.percentage": percentage
            }}
        )
        
        if result.matched_count == 0:
            classroom = db.classrooms.find_one({"c_code": classroom_code})
            db.students.update_one(
                {"student_id": student_id},
                {"$push": {
                    "attendance": {
                        "classroom_code": classroom_code,
                        "classroom_name": classroom.get("name", ""),
                        "present_classes": present_classes,
                        "total_classes": total_classes,
                        "percentage": percentage,
                        "history": []
                    }
                }},
                upsert=True
            )
        
        students = list(db.students.find({"attendance.classroom_code": classroom_code}))
        total_present = sum(
            s["attendance"][0]["present_classes"] 
            for s in students 
            if s["attendance"] and s["attendance"][0]["classroom_code"] == classroom_code
        )
        overall_percentage = round((total_present / (len(students) * total_classes)) * 100) if students and total_classes > 0 else 0
        
        return JSONResponse({
            "success": True,
            "message": "Attendance updated permanently",
            "percentage": percentage,
            "overall_percentage": overall_percentage
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/feedback-for")
async def student_dashboard(request: Request):
    student_id = request.session.get("student_id") 
    if not student_id:
        return {"error": "User not logged in"}
    student = students_collection.find_one({"student_id": student_id})
    if not student:
        return {"error": "Student not found"}
    joined_classes = student.get("classrooms_joined", [])
    return templates.TemplateResponse("feedback_for.html", {
        "request": request,
        "joined_classes": joined_classes
    })

@app.get("/api/verify-students/{classroom_code}")
async def verify_students(classroom_code: str):
    students = list(db.students.find({"classrooms_jointed.c_code": classroom_code}, {
        "student_id": 1, "name": 1, "classrooms_jointed": 1}))
    for student in students:
        student["_id"] = str(student["_id"])
    return JSONResponse({"count": len(students), "students": students})

@app.post("/store-class-code")
async def store_class_code(request: Request):
    data = await request.json()
    class_code = data.get('class_code')
    if not class_code:
        return JSONResponse({"status": "error", "message": "Class code is required"}, status_code=400)
    request.session['class_code'] = class_code
    return JSONResponse({"status": "success", "message": "Class code stored in session"})

@app.get("/submit-feedback")
async def feedback_form(request: Request):
    class_code = request.session.get("class_code")
    if not class_code:
        return RedirectResponse("/")
    teacher = db.teachers.find_one({"classrooms_created.c_code": class_code})
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found for this class code")
    classroom = next((c for c in teacher.get("classrooms_created", []) if c.get("c_code") == class_code), None)
    return templates.TemplateResponse("feedback_form.html", {
        "request": request,
        "teacher_name": teacher.get("name"),
        "classroom_name": classroom.get("classroom_name") if classroom else "Unknown Class",
        "class_code": class_code
    })

@app.post("/submit-feedback")
async def submit_feedback(request: Request):
    try:
        class_code = request.session.get("class_code")
        student_id = request.session.get("student_id")
        if not class_code:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Class code not found in session"})
        if not student_id:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Student ID not found in session"})

        form_data = await request.form()
        feedback_data = {"student_id": student_id, "rating": int(form_data.get("rating"))}
        
        result = db.teachers.update_one(
            {"classrooms_created.c_code": class_code},
            {"$push": {"classrooms_created.$.feedback": feedback_data}}
        )
        
        if result.modified_count == 0:
            return JSONResponse(status_code=404, content={"status": "error", "message": "Failed to store feedback"})
        return JSONResponse(status_code=200, content={"status": "success", "message": "Feedback submitted successfully"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    
@app.get("/teacher-feedback")
async def teacher_feedback(request: Request):
    teacher_id = request.session.get("teacher_id")
    if not teacher_id:
        return RedirectResponse("/teacher-login")
    teacher = db.teachers.find_one({"teacher_id": teacher_id})
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    feedback_data = []
    for classroom in teacher.get("classrooms_created", []):
        for feedback in classroom.get("feedback", []):
            feedback_data.append({
                "classroom_name": classroom.get("classroom_name"),
                "classroom_code": classroom.get("c_code"),
                "student_id": feedback.get("student_id"),
                "rating": feedback.get("rating"),
                "comments": feedback.get("comments"),
                "date": feedback.get("date"),
                "feedback_id": str(feedback.get("_id", ObjectId()))
            })
    
    ratings = [f['rating'] for f in feedback_data]
    avg_rating = sum(ratings)/len(ratings) if ratings else 0
    
    return templates.TemplateResponse("teacher_feedback.html", {
        "request": request,
        "teacher_name": teacher.get("name"),
        "feedbacks": feedback_data,
        "average_rating": round(avg_rating, 1),
        "feedback_count": len(feedback_data)
    })

@app.delete("/teacher-feedback/{feedback_index}")
async def delete_feedback(request: Request, feedback_index: int):
    teacher_id = request.session.get("teacher_id")
    if not teacher_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        teacher = db.teachers.find_one({"teacher_id": teacher_id})
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher not found")
        
        feedback_removed = False
        updated_classrooms = []
        for classroom in teacher.get("classrooms_created", []):
            if "feedback" in classroom:
                try:
                    classroom["feedback"].pop(feedback_index)
                    feedback_removed = True
                except IndexError:
                    continue
            updated_classrooms.append(classroom)
        
        if not feedback_removed:
            raise HTTPException(status_code=404, detail="Feedback not found")
        
        result = db.teachers.update_one(
            {"teacher_id": teacher_id},
            {"$set": {"classrooms_created": updated_classrooms}}
        )
        return JSONResponse(status_code=200, content={"status": "success", "message": "Feedback deleted successfully"})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@app.get("/api-attendance/{classroom_code}/export")
async def export_attendance(classroom_code: str):
    classroom = db.classrooms.find_one({"c_code": classroom_code})
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    students = list(db.students.find({
        "classrooms_joined.c_code": classroom_code
    }))
    
    total_classes = db.attendance.count_documents({"classroom_code": classroom_code})
    
    output = BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Attendance Report"
   
    headers = [
        "Student ID",
        "Student Name",
        "Total Classes",
        "Present Classes",
        "Attendance Percentage"
    ]
    sheet.append(headers)

    for student in students:
        attendance_record = next(
            (item for item in student.get("attendance", []) 
             if item.get("classroom_code") == classroom_code),
            None
        )
        
        present_classes = attendance_record.get("present_classes", 0) if attendance_record else 0
        percentage = attendance_record.get("percentage", 0) if attendance_record else 0
        
        sheet.append([
            student["student_id"],
            student["name"],
            total_classes,
            present_classes,
            f"{percentage}%"
        ])

    for column in sheet.columns:
        max_length = 0
        column = [cell for cell in column]
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = (max_length + 2)
        sheet.column_dimensions[column[0].column_letter].width = adjusted_width
    
    workbook.save(output)
    output.seek(0)

    filename = f"attendance_report_{classroom_code}.xlsx"
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "application/vnd.ms-excel"
        }
    )