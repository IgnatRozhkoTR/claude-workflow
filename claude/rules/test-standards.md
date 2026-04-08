# Test Standards

## What to Test
Unit tests: Services with logic, converters, mappers, validators, calculators, utilities.
Integration tests: Actual DB queries, transaction boundaries, multi-step workflows.
Skip: Simple getters/setters, UI components, frontend, config classes, simple DTOs.

## Structure
Independent tests, AAA pattern (Arrange-Act-Assert), descriptive names.
Coverage: Happy path, edge cases, errors, all branches.
Naming: methodName_shouldDoSomething_whenConditionMet()

## Clean Test Code
DRY: Extract duplicated test setup into helper methods or @BeforeEach.
Methods: Clear arrange-act-assert sections.
Naming: Descriptive test names explaining behavior and conditions.
No placeholder implementations. All test methods must have meaningful assertions.
No TODO comments. All branches and edge cases must be covered.

## Mockito
```java
@ExtendWith(MockitoExtension.class)
class UserServiceTest {
    @Mock private UserRepository userRepository;
    @InjectMocks private UserService userService;

    @Test
    void createUser_shouldReturnUser_whenValidDataProvided() {
        when(userRepository.save(any())).thenReturn(user);
        var result = userService.createUser("john", "john@example.com");
        assertThat(result).isNotNull();
        verify(userRepository).save(any());
    }
}
```

Advanced patterns:
- when(repo.save(any())).thenAnswer(inv -> inv.getArgument(0));
- doThrow(new RuntimeException()).when(service).process(any());
- ArgumentCaptor<User> captor = ArgumentCaptor.forClass(User.class);

## AssertJ
```java
assertThat(users).hasSize(3).extracting(User::getName).containsExactly("a", "b", "c");
assertThatThrownBy(() -> service.get(id)).isInstanceOf(NotFoundException.class);
assertThat(repo.findById(id)).isPresent().get().extracting(User::getName).isEqualTo("john");
```

## TestContainers
```java
@SpringBootTest @Testcontainers
class UserRepositoryIntegrationTest {
    @Container
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:15");

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry r) {
        r.add("spring.datasource.url", postgres::getJdbcUrl);
    }
}
```

## Kotlin MockK
```kotlin
private val repo: UserRepository = mockk()
every { repo.save(any()) } returns user
verify { repo.save(any()) }
```

## Controller Tests
```java
@WebMvcTest(UserController.class)
class UserControllerTest {
    @Autowired MockMvc mockMvc;
    @MockBean UserService userService;

    @Test
    void getUser_shouldReturnUser_whenExists() throws Exception {
        when(userService.getUser(any())).thenReturn(Optional.of(user));
        mockMvc.perform(get("/api/users/{id}", id))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("john"));
    }
}
```
