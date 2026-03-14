# Java Conventions

## Style

IDE: Import project code-style.xml. Auto-format before commit.
var: Use when type clear from RHS.
Annotations: Single on same line. Multiple on separate lines with empty line after.
Entity fields: each annotation on own line.

Field order:
1. @Autowired our services
2. @Autowired Jmix dependencies
3. @ViewComponent UI components
4. @ViewComponent loaders/containers
5. Non-autowired fields
6. Constants

DI Backend: Constructor injection via @RequiredArgsConstructor
DI UI Views: Field injection with @Autowired

Repository: Prefer JmixDataRepository over DataManager.

Match the code style of surrounding code in the same file.

## Implementation Patterns

Stack: Spring Boot, JPA/Hibernate, Jmix

Repository: JmixDataRepository with @Query for custom queries.

Service: Single domain focus, methods under 20 lines.

Controller: Thin controllers, delegate to services.

DTO: Records with validation annotations.

Transactions: @Transactional at service layer. readOnly=true for reads.

Errors: Custom exceptions + @RestControllerAdvice global handler.

Queries: JPQL for entities. Use fetch joins to prevent N+1.

Pagination: Page<T> with PageRequest.of(page, size).

Validation: Bean validation (@NotBlank, @Email, @Positive, @Size).
