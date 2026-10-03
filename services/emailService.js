/**
 * Reusable Email Delivery Service for KANAKKU AI (Node.js / Nodemailer reference).
 * 
 * Uses Gmail SMTP with 16-character App Password to deliver generated daily account PDFs.
 * Note: The active production backend runs FastAPI (Python) using `backend/app/services/email_service.py`.
 * This file is provided for cross-environment compatibility and Node.js backend deployments.
 */

const nodemailer = require('nodemailer');

function formatReportDate(reportDate) {
  if (!reportDate) {
    const today = new Date();
    const d = String(today.getDate()).padStart(2, '0');
    const m = String(today.getMonth() + 1).padStart(2, '0');
    const y = today.getFullYear();
    return `${d}-${m}-${y}`;
  }
  if (typeof reportDate === 'string' && reportDate.includes('-')) {
    const parts = reportDate.split('-');
    if (parts.length === 3 && parts[0].length === 4) {
      return `${parts[2]}-${parts[1]}-${parts[0]}`;
    }
  }
  return String(reportDate);
}

function createTransporter() {
  const user = process.env.GMAIL_USER;
  const pass = process.env.GMAIL_APP_PASSWORD;

  if (!user || !pass) {
    throw new Error('Missing GMAIL_USER or GMAIL_APP_PASSWORD environment variables');
  }

  return nodemailer.createTransport({
    service: 'gmail',
    auth: {
      user: user.trim(),
      pass: pass.trim().replace(/\s+/g, ''),
    },
  });
}

/**
 * Sends Daily Accounting Report PDF to designated recipient via Gmail SMTP.
 * 
 * @param {Object} options
 * @param {Buffer} options.pdfBuffer - Raw PDF buffer
 * @param {string} [options.filename] - Custom attachment filename
 * @param {string|Date} [options.reportDate] - Report date for subject/filename
 * @param {string} [options.recipientEmail] - Recipient email (defaults to REPORT_EMAIL)
 * @param {string} [options.shopName] - Business/Shop name
 * @returns {Promise<Object>} Delivery result object
 */
async function sendDailyReportEmail({
  pdfBuffer,
  filename,
  reportDate,
  recipientEmail,
  shopName = 'Chellam Traders',
}) {
  try {
    if (!pdfBuffer || pdfBuffer.length === 0) {
      return {
        success: false,
        message: 'PDF was generated but email sending failed',
        detail: 'PDF buffer was empty',
      };
    }

    const recipient = recipientEmail || process.env.REPORT_EMAIL;
    if (!recipient) {
      return {
        success: false,
        message: 'PDF was generated but email sending failed',
        detail: 'Missing recipient REPORT_EMAIL configuration',
      };
    }

    const formattedDate = formatReportDate(reportDate);
    const subject = `${shopName} - Daily Account - ${formattedDate}`;
    const attachmentFilename =
      filename || `${shopName.replace(/\s+/g, '-')}-Daily-Account-${formattedDate}.pdf`;

    const transporter = createTransporter();

    const mailOptions = {
      from: `"${shopName}" <${process.env.GMAIL_USER}>`,
      to: recipient,
      subject: subject,
      text: `Hello,

Today's daily account report for ${shopName} is attached to this email.

The report contains:
- Total Sales
- Digital Payments (PP)
- Cash Sales
- Expenses
- Net Cash
- Other existing calculations already included in the PDF

Regards,
KANAKKU AI`,
      attachments: [
        {
          filename: attachmentFilename,
          content: pdfBuffer,
          contentType: 'application/pdf',
        },
      ],
    };

    await transporter.sendMail(mailOptions);

    return {
      success: true,
      message: 'Daily account PDF generated and emailed successfully',
      recipient: recipient,
      attachmentFilename: attachmentFilename,
    };
  } catch (error) {
    // Log detailed error on server only, never expose password
    console.error('Email delivery error:', error.message);
    return {
      success: false,
      message: 'PDF was generated but email sending failed',
      detail: error.message,
    };
  }
}

module.exports = {
  sendDailyReportEmail,
  createTransporter,
};
