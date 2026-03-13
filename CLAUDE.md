# RedTeam Project

## Overview
This project authenticates into RedTeam Flex (flex.redteam.com) and extracts work order data.

## Current Status
- [x] Authentication flow fully implemented (3-layer: Cognito OAuth -> Node backend -> ASP session)
- [x] Work Order 1940046 data fully extracted to `wo_data/` directory
- [x] All tabs and sections pulled (financial overview, changes, RFIs, budget, billing, etc.)

## Scripts
- `login.py` - Basic Cognito SRP login script
- `pull_workorder.py` - Full WO data extraction script (authenticates + pulls all tabs)

## Authentication Flow
1. **OAuth/Cognito**: POST to `auth.redteam.com/connect/login` with email/password/client_id
2. **Node backend**: POST to `node.flex.redteam.com/security/login` with username/password/company
3. **ASP session**: GET the redirect URL from login, then POST to `startapp.asp` with data param

## Key Credentials
- Email: `bnobile@remnantconstruction.com`
- Cognito Password: `Boca5656**`
- Legacy Password: `Boca5656*` (single asterisk)
- Company: `remnantconstruction`
- User Pool ID: `us-east-1_BRaUQRaTR`
- Client ID: `1v7lfl5iq9i0ihdid56llerjf7`

## API Endpoints (node.flex.redteam.com)
- `POST /workorders` - List all workorders
- `GET /workorders/{id}` - Basic WO info
- `GET /workorders/home/id/{id}/mod/{mod}` - Home menu with all sections
- `POST /tabs` - Tab configuration (body: `{TabGroupID, Level, UserID, WorkorderID, WorkorderMod}`)
- `GET /contacts/{id}` - Contacts for a WO
- `POST /contacts` - All contacts
- `GET /workorders/id/{id}/mod/{mod}/spreadsheets` - Spreadsheets
- `GET /security/infoSession` - Session info
- `GET /security/getAccessToken` - JWT access token

## ASP Page Patterns
Tab content is loaded from ASP pages on flex.redteam.com/rts/:
- `app/workorders/activities_/woNews.asp?p={base64params}` - Dashboard
- `app/workorders/budget_/budget_SPEED.asp?woid=&womod=&wostatus=&facilityID=` - Budget
- `app/workorders/dialog_/Documents.asp` - RFI/Correspondence
- `app/workorders/proposal_/contract.asp?WorkorderID=&WorkorderMod=&WorkorderStatus=&FacilityID=` - Contract
- `app/workorders/budget_/ViewProjectSum_L_SPEED.asp` - Financial Overview (View type)
- `app/workorders/changeorder_/views/idxChangesOvw.asp` - Changes Overview (redirect form)
- `app/workorders/dialog_/views/idxRFISummary.asp` - RFI Summary (redirect form)
- `app/asp/LinkWorkorderAttachments.asp` - All attachments

## Dependencies
- pycognito
- requests

## Setup
Dependencies installed via SessionStart hook.

## Session Continuity Tips
- Keep this file updated with current status and next steps
- The SessionStart hook at `.claude/hooks/session-start.sh` runs automatically each session
