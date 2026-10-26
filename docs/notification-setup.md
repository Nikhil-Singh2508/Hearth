# Email and WhatsApp setup

Hearth can send a tenant payment receipt after an owner records a payment. Delivery is attempted only when the tenant has opted in to that channel, and only once when the payment is first recorded. A provider outage does not undo a saved payment. The app currently does not retry failed deliveries or send rent reminders/maintenance notifications.

## Email with Resend

1. Create a Resend account and add a domain you control. Add the SPF and DKIM DNS records shown in the Resend dashboard and wait for the domain to verify.
2. Create an API key with **Sending access**, restricted to that domain.
3. In the project root `.env`, set:

   ~~~dotenv
   RESEND_API_KEY=re_...
   EMAIL_FROM=Hearth <receipts@your-domain.example>
   ~~~

4. Restart the backend. A tenant who enabled email notifications will receive the receipt at their account email after a newly recorded payment.

Resend's official docs: [Python integration](https://resend.com/python), [API key permissions](https://resend.com/changelog/new-api-key-permissions).

## WhatsApp with Meta Cloud API

1. In Meta for Developers, create or select a Meta Business Portfolio and WhatsApp Business Account, add a business phone number, and complete the required verification and account setup.
2. Create a permanent/server-side access token with the WhatsApp messaging permissions required by Meta. Keep it private. Copy the sender's **Phone Number ID** from the WhatsApp API setup screen; do not use the visible phone number in its place.
3. Create and get approval for a WhatsApp message template named `payment_receipt` (or set a different name below). Its body must have exactly four text placeholders, in this order: tenant name, amount, payment method, and received timestamp. Set the language to the template's approved locale.
4. In the project root `.env`, set:

   ~~~dotenv
   WHATSAPP_ACCESS_TOKEN=your-private-token
   WHATSAPP_PHONE_NUMBER_ID=your-phone-number-id
   WHATSAPP_API_VERSION=vXX.X
   WHATSAPP_PAYMENT_TEMPLATE=payment_receipt
   WHATSAPP_TEMPLATE_LANGUAGE=en_US
   ~~~

   Replace `vXX.X` with the currently supported Graph API version shown in Meta's current WhatsApp Cloud API documentation. Use the exact approved template name and language code.
5. Restart the backend. A tenant who has enabled WhatsApp and saved their number in international format will receive the receipt.

The tenant's in-app WhatsApp opt-in is recorded as consent. Keep the approved template and Meta's current WhatsApp business messaging policy in force; use the Meta dashboard to review delivery status and template approval.

## Local configuration and safety

- Put real values in the root `.env`, not `.env.example`, source code, or a frontend `VITE_*` variable. Do not paste provider tokens into chat or commit them.
- `.env` is git-ignored. Copy the variable names from `.env.example`, fill in only the channels you want, and restart the backend after editing.
- The tenant portal reports each channel as configured when its required settings are present. A configured provider alone does not send messages without tenant consent.
- To confirm email delivery, use a tenant account email you control, enable email in that tenant's portal, then record a small test payment as the owner. For WhatsApp, use a consenting test recipient and an approved template.
- Provider rejection/timeout is logged by payment ID without logging the token, phone number, or provider response body. The payment remains recorded, and the API does not currently expose delivery/retry history.

## Current scope

Payment receipts are the first integrated event. Rent reminders, invitations, maintenance updates, delivery webhooks, persistent retry queues, and a delivery history screen still need separate implementation. Delivery calls run after the payment commits, so a crash between commit and provider call can leave a receipt unsent; check the provider dashboard when validating setup.
