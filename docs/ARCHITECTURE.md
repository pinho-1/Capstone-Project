# Architecture

## Overview
Talentum AI Career Mentor is a web application built with FastAPI on the backend and a Jinja2 + HTMX frontend. The system provides AI-assisted career tools including CV analysis, conversational career guidance, career matching, and interview simulation. The backend exposes both HTML-rendering routes and JSON APIs, persists user data in a relational database, and integrates large language models for analysis and generation tasks. Observability is implemented using Langfuse to monitor AI interactions and system behavior.

The application is organized around feature-based routers and service modules, ensuring a clear separation between HTTP handling, business logic, and AI orchestration.

## Architectural Motivation
The technology stack was selected based on a combination of prior experience, academic exposure, cost constraints, and suitability for rapid prototyping.

FastAPI was chosen as the backend framework because at least one member of the group had prior hands-on experience with FastAPI, Jinja2, and HTMX. This allowed the team to move faster and reduce implementation risk while still using a modern, production-grade Python framework. FastAPI also provides strong typing, dependency injection, and asynchronous support, which are well suited for AI-heavy workloads.

Jinja2 and HTMX were used instead of a full frontend framework to keep the architecture simple and server-driven. This choice reduced frontend complexity while still allowing dynamic, interactive user interfaces through partial HTML updates. Given the scope of the project and the team’s familiarity with these tools, this approach was more efficient than introducing React or another SPA framework.

Supabase was selected as the database and authentication backend due to the availability of a free plan that met the project’s requirements. It provides a managed PostgreSQL database with minimal setup overhead and integrates cleanly with SQLAlchemy. This allowed the team to focus on application logic rather than database infrastructure.

Gemini was chosen as the language model provider because it offers a free tier, has a simple API, and was explicitly covered during coursework. Using Gemini reduced both financial cost and learning overhead, while still supporting structured JSON outputs and conversational generation.

Langfuse was selected for observability for similar reasons. It provides a free tier sufficient for development and evaluation, and it was introduced during classes. Langfuse integrates naturally with LLM-based systems and enables trace-level visibility into AI interactions without requiring custom logging infrastructure.

Other architectural decisions, such as in-memory caching and session-based state, were chosen deliberately to balance simplicity and functionality within the project’s academic scope.

## Runtime Flow
A request enters the FastAPI application through the main app configuration. Session middleware resolves the browser session, and authentication utilities determine whether a user is logged in or operating in guest mode.

Page routes render Jinja templates directly, while interactive components use HTMX to fetch HTML partials or JSON responses. API routes are used primarily for chat interactions, interview simulations, and background polling.

AI-related routes construct a controlled context, call the relevant AI service module, validate and sanitize the output, and persist structured results when appropriate. Observability hooks record latency and metadata at key points without storing sensitive user content.

## Project Structure
The backend entry point initializes the FastAPI app, mounts static assets, configures templates, and includes feature routers.

Routers are grouped by feature: authentication, CV analysis, chat assistant, career matching, and interviews. Each router handles HTTP concerns only.

Service modules contain AI prompts, orchestration logic, validation, and post-processing. This separation ensures that AI logic is reusable and testable independently of HTTP endpoints.

Models define SQLAlchemy entities for persistent data such as users, CVs, chat messages, and job applications.

The frontend is composed of Jinja templates and reusable HTMX partials, with static assets served via FastAPI.

## Authentication and Session Management
Authentication is handled through a dedicated router and resolved per request using dependency injection. SessionMiddleware is used to maintain browser session state.

Sessions are required for features such as guest chat identifiers, CV dashboard state, and interview simulations. Guest users are allowed limited access to the chat assistant but are prevented from persisting personal data or using tools that require storage.

This design allows a clear separation between exploratory usage and authenticated, personalized features.

## Database Layer
The database layer uses SQLAlchemy with a PostgreSQL backend provided by Supabase. All database access is scoped through dependency-injected sessions to ensure isolation between requests.

Background tasks, such as CV processing, use a separate session factory to avoid sharing request-scoped database connections across threads.

User-specific queries are always filtered by user identifier to prevent cross-user data access. CV identifiers use UUIDs to avoid predictable URLs.

## CV Analyzer
The CV Analyzer allows users to upload a document and receive structured feedback. Uploaded files are read immediately into memory and processed asynchronously in a background task.

Text extraction supports PDF, DOCX, and TXT formats. The extracted text is first classified to determine whether the document is a CV. If the document is not a CV, scoring is disabled and the user receives guidance on how to reformat the document.

If the document is a CV, the system generates category scores, explanations, and mentor insights. These results are stored in the database and rendered on a dashboard page.

Dynamic mentor cards are generated based on user intents. Novelty control is implemented using playbook dimensions and per-session history to reduce repetition in tips and examples.

## Chat Assistant
The chat assistant supports both authenticated users and guests. Authenticated users have their messages stored in the database, while guests receive a stable per-session identifier without persistence.

An agent orchestrator routes user messages to specialized agents such as general guidance, application tracking, research, writing, or roadmap planning. Tool usage is restricted to cases where it provides real value, and personal tools are gated behind authentication.

This design ensures extensibility while keeping conversational behavior predictable.

## Career Match
The career matching feature compares a user’s CV against job descriptions. Jobs are loaded from a static dataset for the purposes of the project.

The system extracts grounded facts linking job requirements to explicit evidence snippets in the CV. A deterministic scoring algorithm computes a baseline score based on must-have coverage, seniority alignment, and experience signals.

An additional AI-based judgement step refines the score within constrained bounds. Results are cached in memory per process using a key derived from user ID, CV ID, CV update timestamp, and job ID to prevent stale results.

## Interview Simulator
The interview simulator provides a turn-based mock interview experience. Each interview session is identified by a unique session ID and stored in a bounded in-memory store keyed by user ID and session ID.

For each user response, the system generates exactly one recruiter follow-up question. After the final turn, the full conversation is evaluated to produce a final score and structured feedback.

This design avoids storing large conversational histories in the database while still supporting realistic multi-turn interviews.

## AI Integration
All interactions with Gemini are centralized in a single client module. Structured outputs use JSON mode to enforce schema stability.

Strict extraction and scoring tasks use a temperature of zero to reduce variability, while conversational and writing tasks allow slightly higher temperatures for natural output.

Every AI response is validated and sanitized before use to prevent schema drift or hallucinated fields from propagating into the application state.

## Observability
Langfuse is used to track AI interactions and system behavior. Each major user interaction creates or updates a trace identified by a stable session key.

Spans are used to measure latency for AI generation, tool execution, and evaluation steps. Only non-sensitive metadata such as timing, feature name, and final scores is recorded.

The system continues to function normally if Langfuse is not configured, ensuring observability is optional rather than a hard dependency.

## Error Handling and Resilience
Failures in background processing mark the affected resource as failed and return a safe UI state. AI overloads are handled gracefully with retry logic and fallback messages.

All AI outputs are validated, and safe defaults are applied if outputs are missing or malformed. In-memory stores and caches are explicitly bounded to prevent unbounded memory growth.

## Deployment Notes
Static files are served using FastAPI’s StaticFiles. Templates are loaded from the frontend directory.

Environment variables are required for the Gemini API key and optional for Langfuse configuration. SessionMiddleware requires a secret key for stable session handling.
