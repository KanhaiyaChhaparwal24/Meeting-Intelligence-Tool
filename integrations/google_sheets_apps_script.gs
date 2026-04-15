/**
 * Google Sheets Apps Script for per-row Gmail sending.
 *
 * What it adds:
 * - A custom menu: "Meeting Intelligence" → "Setup Send Columns" and "Send Checked Emails"
 * - Optional columns in the "Logs" sheet:
 *     Email | Send? | Sent At | Send Status
 * - A confirmation dialog before sending
 *
 * How to use:
 * 1) Open your Google Sheet: "Meeting Intelligence"
 * 2) Extensions → Apps Script
 * 3) Paste this file into the editor and save
 * 4) Reload the spreadsheet
 * 5) Run: Meeting Intelligence → Setup Send Columns
 * 6) Tick Send? for rows you want to email → Meeting Intelligence → Send Checked Emails
 */

const LOGS_SHEET_NAME = 'Logs';
const TEAM_SHEET_NAME = 'Team Directory';

const COL_TIMESTAMP = 'Timestamp';
const COL_MEETING_ID = 'Meeting_ID';
const COL_SUMMARY = 'Summary';
const COL_TASK = 'Task';
const COL_OWNER = 'Owner';
const COL_DEADLINE = 'Deadline';
const COL_PRIORITY = 'Priority';
const COL_DECISION = 'Decision';
const COL_OPEN_QUESTION = 'Open Question';

// Send-related columns (added if missing)
const COL_EMAIL = 'Email';
const COL_SEND = 'Send?';
const COL_SENT_AT = 'Sent At';
const COL_SEND_STATUS = 'Send Status';

// Demo mode:
// - true  => do NOT send real emails, just mark rows as DEMO in the sheet
// - false => send real emails via GmailApp
const DEMO_MODE = false;

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Meeting Intelligence')
    .addItem('Setup Send Columns', 'setupSendColumns')
    .addItem('Send Checked Emails', 'sendCheckedEmails')
    .addToUi();

  // Auto-ensure send columns exist on open (silent: no popups)
  try {
    setupSendColumns(true);
  } catch (e) {
    console.error(e);
  }
}

function setupSendColumns(silent) {
  const showAlerts = !silent;

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const logs = ss.getSheetByName(LOGS_SHEET_NAME);
  if (!logs) {
    if (showAlerts) SpreadsheetApp.getUi().alert(`Sheet not found: ${LOGS_SHEET_NAME}`);
    return;
  }

  const lastCol = Math.max(logs.getLastColumn(), 1);
  const headerRange = logs.getRange(1, 1, 1, lastCol);
  const headerValues = headerRange.getValues()[0];
  const headers = headerValues.map(h => String(h || '').trim());

  const needed = [COL_EMAIL, COL_SEND, COL_SENT_AT, COL_SEND_STATUS];
  let changed = false;

  needed.forEach(name => {
    if (!headers.includes(name)) {
      headers.push(name);
      changed = true;
    }
  });

  if (changed) {
    logs.getRange(1, 1, 1, headers.length).setValues([headers]);
  }

  const sendCol = headers.indexOf(COL_SEND) + 1;
  const sentAtCol = headers.indexOf(COL_SENT_AT) + 1;

  const lastRow = logs.getLastRow();

  // Add checkboxes for existing rows in Send? column
  if (lastRow >= 2) {
    logs.getRange(2, sendCol, lastRow - 1, 1).insertCheckboxes();

    // Ensure Sent At shows date + time
    logs.getRange(2, sentAtCol, lastRow - 1, 1).setNumberFormat('yyyy-mm-dd hh:mm:ss');
  }

  if (showAlerts) {
    SpreadsheetApp.getUi().alert('Send columns are ready. Tick "Send?" for rows you want to email.');
  }
}

function sendCheckedEmails() {
  const ui = SpreadsheetApp.getUi();
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  const logs = ss.getSheetByName(LOGS_SHEET_NAME);
  const team = ss.getSheetByName(TEAM_SHEET_NAME);

  if (!logs) {
    ui.alert(`Sheet not found: ${LOGS_SHEET_NAME}`);
    return;
  }
  if (!team) {
    ui.alert(`Sheet not found: ${TEAM_SHEET_NAME}`);
    return;
  }

  const headerValues = logs.getRange(1, 1, 1, logs.getLastColumn()).getValues()[0];
  const headers = headerValues.map(h => String(h || '').trim());

  // Ensure send columns exist (auto-setup if missing)
  const required = [COL_OWNER, COL_TASK, COL_DEADLINE, COL_PRIORITY, COL_SEND, COL_SENT_AT, COL_SEND_STATUS];
  let missing = required.filter(c => !headers.includes(c));
  if (missing.length) {
    setupSendColumns(true);

    const headerValues2 = logs.getRange(1, 1, 1, logs.getLastColumn()).getValues()[0];
    const headers2 = headerValues2.map(h => String(h || '').trim());
    headers.length = 0;
    headers.push(...headers2);

    missing = required.filter(c => !headers.includes(c));
    if (missing.length) {
      ui.alert(`Missing columns in Logs: ${missing.join(', ')}`);
      return;
    }
  }

  const idx = (name) => headers.indexOf(name) + 1;

  const ownerCol = idx(COL_OWNER);
  const taskCol = idx(COL_TASK);
  const deadlineCol = idx(COL_DEADLINE);
  const priorityCol = idx(COL_PRIORITY);

  const meetingIdCol = headers.includes(COL_MEETING_ID) ? idx(COL_MEETING_ID) : 0;
  const timestampCol = headers.includes(COL_TIMESTAMP) ? idx(COL_TIMESTAMP) : 0;
  const summaryCol = headers.includes(COL_SUMMARY) ? idx(COL_SUMMARY) : 0;
  const decisionCol = headers.includes(COL_DECISION) ? idx(COL_DECISION) : 0;
  const openQuestionCol = headers.includes(COL_OPEN_QUESTION) ? idx(COL_OPEN_QUESTION) : 0;

  const emailCol = headers.includes(COL_EMAIL) ? idx(COL_EMAIL) : 0;
  const sendCol = idx(COL_SEND);
  const sentAtCol = idx(COL_SENT_AT);
  const statusCol = idx(COL_SEND_STATUS);

  const lastRow = logs.getLastRow();
  if (lastRow < 2) {
    ui.alert('No rows to send.');
    return;
  }

  const teamMap = loadTeamDirectory_(team);

  // Read all needed data in one shot for speed
  const dataRange = logs.getRange(2, 1, lastRow - 1, logs.getLastColumn());
  const rows = dataRange.getValues();

  const toSend = [];
  rows.forEach((row, i) => {
    const send = Boolean(row[sendCol - 1]);
    const alreadySent = String(row[sentAtCol - 1] || '').trim();
    if (!send || alreadySent) return;

    const owner = String(row[ownerCol - 1] || '').trim();
    const task = String(row[taskCol - 1] || '').trim();
    const deadline = String(row[deadlineCol - 1] || '').trim();
    const priority = String(row[priorityCol - 1] || '').trim();

    const meetingId = meetingIdCol ? String(row[meetingIdCol - 1] || '').trim() : '';
    const timestamp = timestampCol ? String(row[timestampCol - 1] || '').trim() : '';
    const summary = summaryCol ? String(row[summaryCol - 1] || '').trim() : '';
    const decision = decisionCol ? String(row[decisionCol - 1] || '').trim() : '';
    const openQuestion = openQuestionCol ? String(row[openQuestionCol - 1] || '').trim() : '';

    // Prefer explicit Email column if present, else lookup by owner
    let email = '';
    let emailFromDirectory = false;
    if (emailCol) {
      email = String(row[emailCol - 1] || '').trim();
    }
    if (!email && owner) {
      email = teamMap[owner.toLowerCase()] || '';
      emailFromDirectory = Boolean(email);
    }

    toSend.push({
      rowIndex: i, // 0-based in rows array
      sheetRow: i + 2, // actual sheet row
      owner,
      email,
      emailFromDirectory,
      task,
      deadline,
      priority,
      meetingId,
      timestamp,
      summary,
      decision,
      openQuestion,
    });
  });

  if (!toSend.length) {
    ui.alert('No checked rows found (or they were already sent).');
    return;
  }

  const previewCount = toSend.length;
  const resp = ui.alert(
    'Send emails?',
    `About to send ${previewCount} email(s). Continue?`,
    ui.ButtonSet.YES_NO
  );
  if (resp !== ui.Button.YES) {
    ui.alert('Cancelled.');
    return;
  }

  // Send and update status
  toSend.forEach(item => {
    try {
      if (!item.email) {
        logs.getRange(item.sheetRow, statusCol).setValue('SKIPPED: missing email');
        logs.getRange(item.sheetRow, sendCol).setValue(false);
        return;
      }

      // If Email was resolved from Team Directory, write it back into the row for visibility.
      if (emailCol && item.emailFromDirectory) {
        logs.getRange(item.sheetRow, emailCol).setValue(item.email);
      }

      const subject = item.meetingId ? `Meeting Action Item (${item.meetingId})` : 'Meeting Action Item';

      const bodyLines = [
        `Hello ${item.owner || 'there'},`,
        '',
        'You have a new meeting action item:',
        '',
        `Task: ${item.task}`,
        `Priority: ${item.priority || 'Medium'}`,
        `Deadline: ${item.deadline || '(no deadline)'}`,
      ];

      if (item.decision) bodyLines.push('', `Decision made: ${item.decision}`);
      if (item.openQuestion) bodyLines.push('', `Open question: ${item.openQuestion}`);
      if (item.summary) bodyLines.push('', `Meeting summary: ${item.summary}`);
      if (item.meetingId) bodyLines.push('', `Meeting ID: ${item.meetingId}`);
      if (item.timestamp) bodyLines.push(`Logged at: ${item.timestamp}`);

      bodyLines.push('', 'Regards,', 'Meeting Intelligence Tool');

      const sentAt = new Date();

      if (DEMO_MODE) {
        logs.getRange(item.sheetRow, sentAtCol).setNumberFormat('yyyy-mm-dd hh:mm:ss');
        logs.getRange(item.sheetRow, sentAtCol).setValue(sentAt);
        logs.getRange(item.sheetRow, statusCol).setValue('DEMO: would send');
        logs.getRange(item.sheetRow, sendCol).setValue(false);
        return;
      }

      GmailApp.sendEmail(item.email, subject, bodyLines.join('\n'));

      logs.getRange(item.sheetRow, sentAtCol).setNumberFormat('yyyy-mm-dd hh:mm:ss');
      logs.getRange(item.sheetRow, sentAtCol).setValue(sentAt);
      logs.getRange(item.sheetRow, statusCol).setValue('SENT');
      logs.getRange(item.sheetRow, sendCol).setValue(false);
    } catch (e) {
      logs.getRange(item.sheetRow, statusCol).setValue(`ERROR: ${String(e)}`);
      // keep Send? checked so user can retry
    }
  });

  ui.alert('Done. Check "Sent At" and "Send Status" columns.');
}

function loadTeamDirectory_(teamSheet) {
  const lastRow = teamSheet.getLastRow();
  const lastCol = teamSheet.getLastColumn();
  if (lastRow < 2 || lastCol < 2) return {};

  const header = teamSheet.getRange(1, 1, 1, lastCol).getValues()[0].map(h => String(h || '').trim());
  const nameIdx = header.indexOf('Name');
  const emailIdx = header.indexOf('Email');
  if (nameIdx === -1 || emailIdx === -1) return {};

  const values = teamSheet.getRange(2, 1, lastRow - 1, lastCol).getValues();
  const map = {};
  values.forEach(row => {
    const name = String(row[nameIdx] || '').trim();
    const email = String(row[emailIdx] || '').trim();
    if (!name || !email) return;
    map[name.toLowerCase()] = extractEmail_(email);
  });

  return map;
}

function extractEmail_(value) {
  const v = String(value || '').trim();
  if (!v) return '';
  const lower = v.toLowerCase();

  if (lower.includes('mailto:')) {
    const idx = lower.indexOf('mailto:');
    return v.substring(idx + 'mailto:'.length).replace(')', '').trim();
  }

  // [x](mailto:y)
  const m = v.match(/\]\(([^)]+)\)$/);
  if (m && m[1]) {
    const inner = String(m[1]);
    if (inner.toLowerCase().includes('mailto:')) return extractEmail_(inner);
  }

  return v;
}
