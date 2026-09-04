

def registration_template(user_name):
        return f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 10px; background-color: #ffffff;">
                <div style="background-color: #0284c7; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h1 style="color: #ffffff; margin: 0; font-size: 24px;">MediCare</h1>
                </div>
        
                <div style="padding: 20px; color: #334155;">
                    <h2 style="color: #0f172a; margin-top: 0;">Welcome, { user_name }! 🎉</h2>
                    <p>Thank you for registering with <b>MediCare Pro</b>. Your account has been successfully created.</p>
        
                    <p>You can now log in to access your dashboard, book appointments with doctors, and manage your health records seamlessly.</p>
        
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="https://clinical-system.com/login" style="background-color: #0284c7; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; display: inline-block;">Log In to Your Account</a>
                    </div>
        
                    <p style="color: #64748b; font-size: 14px;">If you didn't create this account, please ignore this email or contact support.</p>
                </div>
        
                <div style="border-top: 1px solid #e2e8f0; padding-top: 15px; text-align: center; color: #94a3b8; font-size: 12px;">
                    &copy; 2026 MediCare . All rights reserved.
                </div>
            </div>  
        """


def send_otp_template(otp_code):
    return f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 10px; background-color: #ffffff;">
            <div style="background-color: #0284c7; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                <h1 style="color: #ffffff; margin: 0; font-size: 24px;">Coastal Solution</h1>
            </div>
        
            <div style="padding: 25px; color: #334155;">
                <h2 style="color: #0f172a; margin-top: 0; font-size: 20px;">Your Verification Code</h2>
                
                <p style="font-size: 15px; line-height: 1.5;">Hello,</p>
                
                <p style="font-size: 15px; line-height: 1.5;">Use the OTP code below to verify your account or complete your request on MediCare Pro:</p>
        
                <div style="text-align: center; margin: 30px 0;">
                    <div style="background-color: #f1f5f9; border: 2px dashed #0284c7; padding: 15px 30px; font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #0284c7; display: inline-block; border-radius: 8px;">
                        { otp_code }
                    </div>
                </div>
        
                <p style="font-size: 14px; color: #ef4444; text-align: center; font-weight: 500;">
                    ⏰ This code will expire in 5 minutes.
                </p>
        
                <p style="font-size: 13px; color: #94a3b8; margin-top: 25px;">
                    If you did not request this verification code, please ignore this email. Do not share this code with anyone.
                </p>
            </div>
        
            <div style="border-top: 1px solid #e2e8f0; padding-top: 15px; text-align: center; color: #94a3b8; font-size: 12px;">
                &copy; 2026 Coastal Solution. All rights reserved.
            </div>
        </div>
    """
