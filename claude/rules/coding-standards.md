# Coding Standards

## SOLID

SRP: Each class one reason to change. Each method one thing.
If you need "and" to describe it, split it.

OCP: Open for extension, closed for modification.
Add new functionality via new classes, not modifying existing.
Use abstract classes and interfaces for extension points.

Focus on SRP and OCP. Other principles (Liskov, DI) are good but not primary focus.
Don't over-engineer - keep simple until complexity needed.

## Clean Code

DRY: Every knowledge piece has single authoritative representation.

Exceptions: Specific exceptions with meaningful context, never generic Exception.

Null handling: Never pass or return null.
- Return Optional for absent values
- Return empty collections
- Throw exception if absence is exceptional

Optional: use for return values and chaining. Don't use for params, entity fields, collections.

Methods: One thing at one abstraction level. Keep under 20 lines.

Naming:
- Classes: Nouns
- Methods: Verbs
- Variables: Descriptive
- Booleans: Questions (isValid, hasPermission)
- Constants: UPPER_SNAKE

Constants: Use for non-obvious meanings or reused config. Don't over-abstract obvious values.

Organization: Group related functionality. Dependencies flow one direction.

## No Comments

No technical comments explaining HOW code works.
Self-documenting: Clear naming, small focused methods, proper structure.
Exception: Business logic WHY comments only - requirements not obvious from code.
Instead of comments: Rename variables/methods, extract to well-named methods, use descriptive constants.

## No Placeholders

Forbidden:
- return true/false as placeholder
- throw NotImplementedException
- throw UnsupportedOperationException
- TODO comments
- Empty method bodies
- Hardcoded values where logic should exist

Required: Complete implementation, all code paths handled, proper error handling, meaningful return values.
