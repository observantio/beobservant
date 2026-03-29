import {
  getRoleVariant,
  getUserInitials,
} from "../userUiUtils";
import {
  USERNAME_REGEX,
  EMAIL_REGEX,
  buildCreateUserPayload,
  generateStrongPassword,
  validateCreateUserForm,
} from "../createUserFormUtils";

describe("user UI helpers", () => {
  it("maps role variants", () => {
    expect(getRoleVariant("admin")).toBe("error");
    expect(getRoleVariant("user")).toBe("warning");
    expect(getRoleVariant("viewer")).toBe("success");
    expect(getRoleVariant("unknown")).toBe("default");
  });

  it("builds initials from full_name, username, and fallback", () => {
    expect(getUserInitials({ full_name: "Jane Doe", username: "jdoe" })).toBe("JD");
    expect(getUserInitials({ username: "solo" })).toBe("S");
    expect(getUserInitials({})).toBe("U");
  });
});

describe("create user form utils", () => {
  it("exports username/email regex", () => {
    expect(USERNAME_REGEX.test("john_doe")).toBe(true);
    expect(USERNAME_REGEX.test("Bad Name")).toBe(false);
    expect(EMAIL_REGEX.test("a@b.com")).toBe(true);
    expect(EMAIL_REGEX.test("bad-email")).toBe(false);
  });

  it("generates strong passwords with requested length", () => {
    const password = generateStrongPassword(24);
    expect(password).toHaveLength(24);
  });

  it("validates create form with required password", () => {
    const result = validateCreateUserForm(
      { username: "AB", email: "bad", password: "123" },
      { requirePassword: true },
    );

    expect(result.errors.username).toBeTruthy();
    expect(result.errors.email).toBeTruthy();
    expect(result.errors.password).toBeTruthy();
  });

  it("validates optional password mode and normalizes data", () => {
    const result = validateCreateUserForm(
      { username: " Alice ", email: " alice@example.com ", password: "" },
      { requirePassword: false },
    );

    expect(result.errors.password).toBeUndefined();
    expect(result.normalized.username).toBe("alice");
    expect(result.normalized.email).toBe("alice@example.com");
  });

  it("builds payload and omits password when requested", () => {
    const formData = {
      username: " Alice ",
      email: " alice@example.com ",
      password: "secret123",
      role: "user",
    };

    const withPassword = buildCreateUserPayload(formData, {
      includePassword: true,
    });
    const withoutPassword = buildCreateUserPayload(formData, {
      includePassword: false,
    });

    expect(withPassword.password).toBe("secret123");
    expect(withPassword.username).toBe("alice");
    expect(withPassword.email).toBe("alice@example.com");
    expect(withoutPassword.password).toBeUndefined();
  });
});
