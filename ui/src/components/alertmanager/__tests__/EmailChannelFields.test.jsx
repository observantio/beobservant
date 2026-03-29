import { fireEvent, render, screen } from "@testing-library/react";
import EmailChannelFields from "../channelForms/EmailChannelFields";

vi.mock("../../ui", () => ({
  Input: (props) => <input {...props} />,
  Select: ({ children, ...props }) => <select {...props}>{children}</select>,
}));

vi.mock("../../HelpTooltip", () => ({
  default: () => <span>?</span>,
}));

describe("EmailChannelFields", () => {
  it("covers smtp/password branch and updates fields", () => {
    const setFormData = vi.fn();
    const formData = {
      config: {
        to: "alerts@example.com",
        emailProvider: "smtp",
        smtpFrom: "watchdog@example.com",
        smtpHost: "smtp.example.com",
        smtpPort: 587,
        smtpAuthType: "password",
        smtpUsername: "user",
        smtpPassword: "secret",
        smtpStartTLS: false,
        smtpUseSSL: false,
      },
    };

    render(<EmailChannelFields formData={formData} setFormData={setFormData} />);

    const inputs = screen.getAllByRole("textbox");
    fireEvent.change(inputs[0], { target: { value: "team@example.com" } });
    fireEvent.change(inputs[1], { target: { value: "sender@example.com" } });
    fireEvent.change(inputs[2], { target: { value: "smtp.mail" } });
    fireEvent.change(inputs[3], { target: { value: "operator" } });

    const passwordInput = screen.getByPlaceholderText("••••••••");
    fireEvent.change(passwordInput, { target: { value: "new-secret" } });

    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "2525" } });

    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[1], { target: { value: "none" } });

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);

    expect(setFormData).toHaveBeenCalled();
  });

  it("covers smtp api_key and provider switch branches", () => {
    const setFormData = vi.fn();
    const { rerender } = render(
      <EmailChannelFields
        formData={{
          config: {
            emailProvider: "smtp",
            smtpAuthType: "api_key",
            smtpApiKey: "k1",
          },
        }}
        setFormData={setFormData}
      />,
    );

    expect(screen.getByText(/SMTP API Key/i)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("••••••••"), {
      target: { value: "k2" },
    });

    const deliverySelect = screen.getAllByRole("combobox")[0];
    fireEvent.change(deliverySelect, { target: { value: "sendgrid" } });

    rerender(
      <EmailChannelFields
        formData={{
          config: {
            emailProvider: "sendgrid",
            sendgridApiKey: "SG.x",
          },
        }}
        setFormData={setFormData}
      />,
    );

    expect(screen.getByText(/SendGrid API Key/i)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("SG.xxxxx"), {
      target: { value: "SG.abc" },
    });

    rerender(
      <EmailChannelFields
        formData={{
          config: {
            emailProvider: "resend",
            resendApiKey: "re_x",
          },
        }}
        setFormData={setFormData}
      />,
    );

    expect(screen.getByText(/Resend API Key/i)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("re_xxxxx"), {
      target: { value: "re_new" },
    });

    expect(setFormData).toHaveBeenCalled();
  });
});
