Architecture Overview

1. High-Level Architecture

The application follows a layered, service-oriented architecture designed to support a production-ready AI-powered web application with a conversational interface. The system is structured around a clear separation of responsibilities that improves maintainability, scalability, and clarity during development and evaluation.

At a high level, the architecture is composed of a presentation layer responsible for user interaction, an application layer that handles request flow and orchestration, an AI service layer that manages LLM interaction and reasoning, a data layer that persists application state, and an observability layer that tracks and monitors AI behavior across the system.

2. Backend Framework

The backend is implemented using FastAPI in Python. FastAPI was chosen due to its asynchronous support, dependency injection system, and suitability for production-grade APIs. This framework enables efficient handling of concurrent requests and clean separation between routing logic and business logic.

The backend serves both HTML-rendered pages and JSON endpoints. HTML routes are used for pages such as chat, onboarding, CV analyzer, and interviews, while JSON endpoints handle conversational messages, chat history retrieval, and tool execution.

3. Conversational Interface

The application’s primary interaction mechanism is a multi-turn conversational interface. Users interact with the system through a chat-based UI that supports follow-up questions, iterative refinement, and contextual continuity across messages.

Conversational state is maintained using SDK-managed chat sessions. Each session persists across multiple user messages, allowing the AI to reason with prior context rather than responding statelessly. Authenticated users are associated with sessions keyed by their user identifier, while guest users are assigned a stable session identifier stored at the browser session level.

This design allows meaningful interaction for guests while reserving stateful features such as application tracking and history persistence for authenticated users.

4. AI Service Layer
4.1 LLM Integration

The AI service layer integrates a large language model provided by Google Gemini, using the gemini-2.5-flash-lite model via the official SDK. The application uses SDK-managed chat sessions rather than manually reconstructing conversation history, ensuring reliable multi-turn behavior and reduced prompt management complexity.

Prompting is structured around a system prompt that defines global behavior and constraints. Structured user context derived from onboarding data and application metadata is injected into the prompt as trusted JSON. When available, excerpts from the user’s CV are also injected to personalize responses. CV text is truncated to control prompt size and avoid unnecessary noise.

4.2 Multi-Agent Design

The chatbot is implemented as a multi-agent system coordinated by a central orchestrator. Incoming messages are first processed by a router agent that determines which specialist agent is best suited to handle the request.

Specialist agents include a general agent for default conversational behavior, an applications agent for job application tracking and management, a research agent for company and career-related guidance, a writing agent for drafting professional content such as cover letters and outreach messages, and a roadmap agent for generating short-term career plans. Each agent maintains its own conversational session, preventing context leakage between different types of tasks.

5. Function Calling and Tools

The system extends the language model’s capabilities through function calling, enabling deterministic execution of actions that require database interaction or structured updates.

Implemented tools allow users to track job applications, list existing applications, update application statuses, and set follow-up reminders. When the model determines that a tool is required, it issues a structured function call. The backend executes the corresponding operation and returns the result to the model, which then produces a final user-facing response.

This design ensures safe execution, clear separation between reasoning and action, and reliable persistence of user data. Guest users are explicitly restricted from tools that require persistent storage.

6. Document Ingestion

User CVs are ingested as extracted raw text and stored in the database. During chat interactions, the system retrieves the most recent CV associated with the user and selectively injects relevant excerpts into the AI prompt.

Document ingestion is used to personalize responses, improve relevance of feedback, and enable CV-aware recommendations. This feature directly enhances conversational quality rather than existing solely to satisfy technical requirements.

7. Data Layer

The data layer is implemented using SQLAlchemy as the ORM. Core models include users, CVs, chat messages, and job applications. Chat history and application data are persisted only for authenticated users, ensuring privacy and preventing unnecessary storage for guest sessions.

Database interactions are handled within the application layer, keeping AI logic decoupled from persistence concerns.

8. Observability and Monitoring

The system integrates Langfuse for observability and tracing. Tracing is applied across the conversational pipeline, including message handling, agent routing, tool execution, and orchestrator logic.

Each AI interaction is tagged with session identifiers and metadata indicating user or guest context. This enables debugging, monitoring of AI behavior, and post-hoc analysis of decision flows.

9. Deployment Considerations

The application is designed to be deployed as a publicly accessible web service. Configuration is handled via environment variables for secrets and API keys. The architecture supports horizontal scaling of stateless routes and isolates stateful concerns within the database and AI session management.

10. Design Principles

The architecture prioritizes purpose-driven features, ensuring that agents and tools exist only where they add real value. Responsibilities are clearly separated across layers to improve maintainability and reasoning clarity. Defensive design choices are applied throughout, including guest restrictions, error handling, and overload protection. The system is designed to be extensible, allowing new agents or tools to be added without refactoring core logic.

11. Alignment with Capstone Requirements

This architecture satisfies the capstone requirements by providing a Python backend, explicit LLM integration, a multi-turn conversational interface, real function calling tools, meaningful document ingestion, clean architectural separation, integrated observability, and deployment readiness.