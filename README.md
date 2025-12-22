# Talentum AI – Career Mentor

## Overview
**Talentum AI Career Mentor** is an AI-powered web application designed to support students and early‑career professionals in improving their career readiness.  
The platform integrates CV analysis, career matching, conversational mentoring, and mock interview simulations using Large Language Models (LLMs).

This project was developed as part of an academic capstone and prioritizes **system design, responsible AI usage, and architectural clarity** over pure model performance.

---

## Core Features
- **CV Analyzer** with automated scoring and mentor-style feedback  
- **Conversational Career Assistant** with intent routing  
- **Career Match** between CVs and job descriptions  
- **Mock Interview Simulator** with turn-based interaction and final evaluation  
- **Guest mode** and authenticated user flows  
- **LLM observability and tracing**

---

## Technology Stack

### Backend
- Python  
- FastAPI  
- SQLAlchemy  

### Frontend
- Jinja2  
- HTMX  
- Vanilla JavaScript  
- CSS  

### Database
- Supabase (PostgreSQL)

### Deployment
- React

### AI & Observability
- Google Gemini  
- Langfuse  

---

## Architectural Justification

FastAPI combined with Jinja2 and HTMX was selected because at least one member of the group had prior experience with these technologies. This reduced development risk and enabled faster iteration while still maintaining a modern, well-structured backend architecture.

FastAPI offers native asynchronous support, dependency injection, and strong typing, which are particularly valuable in AI-driven applications.  
Jinja2 and HTMX were chosen instead of a full SPA framework to keep the frontend server-driven and lightweight while still supporting dynamic interactions through partial HTML updates.

Supabase was selected as the database provider due to its **free plan**, ease of setup, and managed PostgreSQL offering. It integrates seamlessly with SQLAlchemy and removes the need for custom infrastructure management.

Google Gemini was chosen as the LLM provider because it provides a free tier, has a straightforward API, and was covered during coursework. This reduced both financial cost and learning overhead while still supporting structured JSON outputs and conversational generation.

Langfuse was selected for observability for the same reasons: availability of a free tier and prior exposure during classes. It enables trace-level visibility into AI interactions without requiring custom-built monitoring tools.

Other design decisions, such as session-based state, background task processing, and in-memory caching, were made to balance simplicity, performance, and academic scope.

---

## System Architecture
The application follows a **modular, feature-based architecture**.

Requests enter the FastAPI application and are routed through feature-specific routers.  
Session middleware resolves authentication and user state.  

Pages are rendered using Jinja templates, while interactive components use HTMX to request partial HTML or JSON responses.  
AI-related routes construct controlled prompts, validate outputs, and persist structured results when applicable.

Observability hooks are placed at key AI interaction points to capture execution metadata without storing sensitive content.

---

## Project Structure

```
backend/
  app.py
  database.py
  oauth.py
  models/
  routers/
  services/
  utils/
  data/
frontend/
  pages/
  static/
docs/
requirements.txt
.env.example
README.md
```

---

## Authentication & Sessions
Authentication is handled through a dedicated router and resolved per request using FastAPI dependencies.  
Session middleware maintains browser-level state.

Guest users can explore limited features, while authenticated users gain access to persistent functionality such as CV storage and interview sessions.

---

## Database Layer
The database layer uses SQLAlchemy with PostgreSQL provided by Supabase.

Database sessions are request-scoped and injected via FastAPI dependencies.  
Background tasks create isolated database sessions to prevent concurrency issues.

All user-related queries are scoped by user identifier to ensure data isolation.

---

## CV Analyzer
Users upload CV documents in **PDF, DOCX, or TXT** format.

Files are read immediately and processed asynchronously.  
The system first classifies whether the upload is a CV:
- If **not a CV**, scoring is disabled and corrective guidance is shown.
- If **a CV**, the system generates scores, explanations, and mentor insights.

Results are stored and displayed in a dashboard.  
Dynamic mentor cards adapt to user intent and apply novelty control to avoid repetition.

---

## Career Chat
The chat assistant supports both guest and authenticated users.

Messages are routed to specialized agents based on detected intent.  
Authenticated users benefit from persisted context, while guest sessions remain ephemeral.

---

## Career Match
The career match feature compares CV content against job descriptions.

The system extracts grounded facts, links job requirements to explicit CV evidence, and computes a deterministic baseline score.  
An additional AI judgement refines the score within constrained bounds.

Results are cached in memory to reduce repeated computation.

---

## Interview Simulator
The interview simulator provides a turn-based mock interview experience.

Each session is tracked in memory using a unique session identifier.  
After the final turn, the full conversation is evaluated to produce:
- A final score
- Structured, actionable feedback

This approach avoids storing large conversation logs while maintaining realistic interaction.

---

## AI Integration
All LLM interactions are centralized in a single client module.

Structured tasks enforce JSON-only responses for stability and validation.  
Lower temperatures are used for evaluation tasks, while conversational features allow controlled variability.

All model outputs are sanitized before use.

---

## Observability
Langfuse is used to trace AI interactions and measure latency.

Traces are linked to stable session identifiers and capture only non-sensitive metadata.  
The system remains fully functional if observability is disabled.

---

## Installation & Setup
Python 3.10 or higher is required.

After cloning the repository:
1. Create and activate a virtual environment
2. Install dependencies
3. Configure environment variables

Required environment variables:
- Gemini API key
- Session secret

Langfuse configuration is optional.

The application is started using an ASGI-compatible server.

---

## Usage
Users can explore the platform in guest mode or create an account for full functionality.

Typical flows include:
- CV upload and analysis
- Career chat interaction
- Job matching
- Interview practice

---

## Deployment
The application can be deployed on any platform that supports Python ASGI applications.

---

## Team
**João Pinho**  
Backend development, AI integration, system architecture

**Beatriz Gil**  
AI Assistant Tab, Backend Development 

**Bruno Henriques**  
Career Match Tab 

**Pedro Gouveia**  
Interviews Tab 

---

## License
This project was developed exclusively for academic purposes.
