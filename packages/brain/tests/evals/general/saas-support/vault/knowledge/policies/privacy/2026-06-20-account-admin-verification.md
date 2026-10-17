---
id: account-admin-verification
title: Verify the account admin first
summary: Talk about invoices, billing or payer data only with a verified admin on the account, and never show full bank or card numbers.
area: policies
topic: privacy
kind: rule
scope: company
status: approved
load: domain
added: 2026-06-20
source: Noor Haddad, in conversation
supersedes: none
applies_to: policies/privacy
must_text: Share billing, invoice, payer or bank details only with a verified account admin, replying to the admin email on file; never show full card or bank account numbers anywhere.
asked_as:
  - Someone not on the account wants copies of invoices
  - Can I tell this person their billing details?
  - Customer wants to transfer the account to a new owner
  - Can I paste the card number in my reply?
  - A request came from a different email, okay to send the export?
  - How do I confirm I'm talking to the account admin?
  - Write a reply to a billing request from an unknown address
applies_when: Answering anything about billing, invoices, data exports or ownership on an account.
not_when: General how-to product questions that touch no account data.
role: rule
suggested_triggers:
  - data export
  - billing question
  - change owner
  - invoice copy
  - card number
  - bank details
  - account transfer
  - who is the admin
enriched: 2026-10-16
enriched_by: model:claude-test-data
enriched_hash: 1b5a6f43a109cce9
---
Tallyline accounts hold our customers' invoices plus their own customers' contact and bank details. Before answering anything about billing, invoices, data exports or account ownership, check the person is listed as an admin; if the request came from some other address, reply only to the admin email on file. Last 4 digits only for cards and bank accounts, in tickets, chat and articles alike. Ownership transfers need the signed transfer form and a yes from the current admin.
