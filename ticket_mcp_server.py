"""Standalone local ticketing MCP server.
Install: python -m pip install fastmcp==3.4.11 mcp==1.30.0
Connect using an MCP client over stdio; it launches this script automatically.
Optional localhost URL: python ticket_mcp_server.py --transport http
Tools: 12 ticket tools, 1 deletion tool, 4 extra dummy tools.
Persistent SQLite storage: data/tickets.db beside this file (or --db PATH).
Profiles: --profile all (default), support, or read-only.
This is a local single-user demo without authentication.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def clean(value, label):
    value = value.strip()
    if not value:
        raise ValueError(f"{label} cannot be empty")
    return value


class TicketStore:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_no INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT NOT NULL, issue TEXT NOT NULL,
                    priority TEXT NOT NULL, status TEXT NOT NULL,
                    assignee TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_no INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_no INTEGER NOT NULL REFERENCES tickets(ticket_no) ON DELETE CASCADE,
                    action TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL
                );
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def require(self, db, ticket_no):
        row = db.execute('SELECT * FROM tickets WHERE ticket_no=?', (ticket_no,)).fetchone()
        if row is None:
            raise ValueError(f'Ticket #{ticket_no} not found')
        return dict(row)

    def event(self, db, ticket_no, action, details):
        db.execute('INSERT INTO events(ticket_no,action,details,created_at) VALUES(?,?,?,?)',
                   (ticket_no, action, json.dumps(details), now()))

    def create(self, product_name, issue, priority='normal'):
        product_name, issue = clean(product_name, 'Product name'), clean(issue, 'Issue')
        if priority not in {'normal', 'high', 'urgent'}:
            raise ValueError('Priority must be normal, high, or urgent')
        with self.connect() as db:
            # Serialize the duplicate check and insert across simultaneous clients.
            db.execute('BEGIN IMMEDIATE')
            for row in db.execute("SELECT * FROM tickets WHERE status != 'closed'"):
                if (row['product_name'].casefold() == product_name.casefold()
                        and row['issue'].casefold() == issue.casefold()):
                    return {'action': 'already_exists', 'ticket': dict(row)}
            timestamp = now()
            cur = db.execute('''INSERT INTO tickets
                (product_name,issue,priority,status,created_at,updated_at)
                VALUES(?,?,?,'open',?,?)''', (product_name, issue, priority, timestamp, timestamp))
            ticket_no = cur.lastrowid
            self.event(db, ticket_no, 'created', {'priority': priority})
            return {'action': 'created', 'ticket': self.require(db, ticket_no)}

    def get(self, ticket_no):
        with self.connect() as db:
            return self.require(db, ticket_no)

    def list(self, status=None, query=None, limit=50, offset=0):
        if status is not None and status not in {'open', 'in_progress', 'closed'}:
            raise ValueError('Status must be open, in_progress, or closed')
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError('Limit must be 1..200 and offset must be nonnegative')
        clauses, args = [], []
        if status:
            clauses.append('status=?'); args.append(status)
        if query:
            clauses.append('(instr(lower(product_name),lower(?))>0 OR instr(lower(issue),lower(?))>0)')
            args.extend([query, query])
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self.connect() as db:
            total = db.execute('SELECT count(*) FROM tickets' + where, args).fetchone()[0]
            rows = db.execute('SELECT * FROM tickets' + where + ' ORDER BY ticket_no DESC LIMIT ? OFFSET ?',
                              args + [limit, offset]).fetchall()
            return {'tickets': [dict(row) for row in rows], 'total': total,
                    'limit': limit, 'offset': offset}

    def change(self, ticket_no, action, fields, details=None, require_open=False, require_closed=False):
        allowed = {'status', 'priority', 'assignee'}
        if not fields or not set(fields) <= allowed:
            raise ValueError('Invalid update fields')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = self.require(db, ticket_no)
            if require_closed and old['status'] != 'closed':
                return {'action': 'already_active', 'ticket': old}
            if require_open and old['status'] == 'closed':
                raise ValueError('Ticket is closed; reopen it first')
            if all(old[key] == value for key, value in fields.items()):
                return {'action': 'unchanged', 'ticket': old}
            assignments = ','.join(f'{key}=?' for key in fields)
            db.execute(f'UPDATE tickets SET {assignments},updated_at=? WHERE ticket_no=?',
                       [*fields.values(), now(), ticket_no])
            self.event(db, ticket_no, action, details or fields)
            return {'action': action, 'ticket': self.require(db, ticket_no)}

    def escalate(self, ticket_no, reason):
        reason = clean(reason, 'Reason')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            ticket = self.require(db, ticket_no)
            if ticket['status'] == 'closed':
                raise ValueError('Ticket is closed; reopen it first')
            if ticket['priority'] in {'high', 'urgent'}:
                return {'action': 'already_escalated', 'ticket': ticket}
            db.execute("UPDATE tickets SET priority='high',updated_at=? WHERE ticket_no=?", (now(), ticket_no))
            self.event(db, ticket_no, 'escalated', {'reason': reason, 'priority': 'high'})
            return {'action': 'escalated', 'ticket': self.require(db, ticket_no)}

    def comment(self, ticket_no, text, author):
        text, author = clean(text, 'Comment'), clean(author, 'Author')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.require(db, ticket_no)
            self.event(db, ticket_no, 'comment', {'text': text, 'author': author})
            db.execute('UPDATE tickets SET updated_at=? WHERE ticket_no=?', (now(), ticket_no))
            return {'action': 'comment_added', 'ticket': self.require(db, ticket_no)}

    def history(self, ticket_no):
        with self.connect() as db:
            self.require(db, ticket_no)
            events = [dict(row) for row in db.execute(
                'SELECT * FROM events WHERE ticket_no=? ORDER BY event_no', (ticket_no,))]
            for event in events:
                event['details'] = json.loads(event['details'])
            return {'ticket_no': ticket_no, 'events': events}

    def stats(self):
        with self.connect() as db:
            return {'total': db.execute('SELECT count(*) FROM tickets').fetchone()[0],
                    'by_status': dict(db.execute('SELECT status,count(*) FROM tickets GROUP BY status')),
                    'by_priority': dict(db.execute('SELECT priority,count(*) FROM tickets GROUP BY priority'))}

    def delete(self, ticket_no, confirm):
        if not confirm:
            raise ValueError('Permanent deletion requires confirm=true. Close tickets to retain history.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.require(db, ticket_no)
            db.execute('DELETE FROM tickets WHERE ticket_no=?', (ticket_no,))
            return {'action': 'deleted', 'ticket_no': ticket_no, 'history_deleted': True}


import argparse
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

READ_TOOLS = {
    'ticket_get', 'ticket_list', 'ticket_history', 'ticket_stats',
}
SUPPORT_TOOLS = READ_TOOLS | {
    'ticket_raise', 'ticket_add_comment', 'ticket_assign', 'ticket_set_status',
    'ticket_escalate', 'ticket_set_priority', 'ticket_close', 'ticket_reopen',
}
PROFILES = ('all', 'support', 'read-only')
DEFAULT_DB = Path(__file__).resolve().parent / 'data' / 'tickets.db'


def build_server(db_path=DEFAULT_DB, profile='all'):
    if profile not in PROFILES:
        raise ValueError('Unknown tool profile')
    store = TicketStore(db_path)
    mcp = FastMCP('Dummy Ticket Desk')

    def expose(group, read_only=False):
        def register(fn):
            selected = (profile == 'all' or (profile == 'support' and fn.__name__ in SUPPORT_TOOLS)
                        or (profile == 'read-only' and fn.__name__ in READ_TOOLS))
            if selected:
                mcp.tool(name=fn.__name__, tags={group}, annotations={
                    'readOnlyHint': read_only,
                    'destructiveHint': fn.__name__ == 'admin_delete_ticket',
                    'openWorldHint': False,
                })(fn)
            return fn
        return register

    @expose('tickets')
    def ticket_raise(product_name: str, issue: str,
                     priority: Literal['normal', 'high', 'urgent'] = 'normal') -> dict:
        """Create a ticket, or return an active ticket with the same product and exact issue.

        product_name: Affected product. issue: Problem description. priority: Initial priority.
        """
        return store.create(product_name, issue, priority)

    @expose('tickets', True)
    def ticket_get(ticket_no: int) -> dict:
        """Read a ticket's current status, priority, assignee, and timestamps by number."""
        return store.get(ticket_no)

    @expose('tickets', True)
    def ticket_list(status: Literal['open', 'in_progress', 'closed'] | None = None,
                    query: str | None = None, limit: int = 50, offset: int = 0) -> dict:
        """List or search tickets by product/issue. Filter status; paginate with limit and offset."""
        return store.list(status, query, limit, offset)

    @expose('tickets')
    def ticket_add_comment(ticket_no: int, text: str, author: str = 'customer') -> dict:
        """Append a comment to ticket history. Does not change status or priority."""
        return store.comment(ticket_no, text, author)

    @expose('tickets')
    def ticket_assign(ticket_no: int, assignee: str) -> dict:
        """Assign an active ticket to a named demo support agent or team."""
        return store.change(ticket_no, 'assigned', {'assignee': clean(assignee, 'Assignee')}, require_open=True)

    @expose('tickets')
    def ticket_set_status(ticket_no: int, status: Literal['open', 'in_progress']) -> dict:
        """Change an active ticket's status. Use ticket_close or ticket_reopen for closure/reopening."""
        return store.change(ticket_no, 'status_changed', {'status': status}, require_open=True)

    @expose('tickets')
    def ticket_escalate(ticket_no: int, reason: str) -> dict:
        """Raise an active ticket to high priority; never downgrade an urgent ticket. Supply reason."""
        return store.escalate(ticket_no, reason)

    @expose('tickets')
    def ticket_set_priority(ticket_no: int, priority: Literal['normal', 'high', 'urgent'], reason: str) -> dict:
        """Explicitly change an active ticket's priority, including a downgrade, with a reason."""
        return store.change(ticket_no, 'priority_changed', {'priority': priority},
                            {'priority': priority, 'reason': clean(reason, 'Reason')}, require_open=True)

    @expose('tickets')
    def ticket_close(ticket_no: int, resolution: str) -> dict:
        """Close a ticket while retaining history. Supply the resolution or closing reason."""
        return store.change(ticket_no, 'closed', {'status': 'closed'},
                            {'resolution': clean(resolution, 'Resolution')})

    @expose('tickets')
    def ticket_reopen(ticket_no: int, reason: str) -> dict:
        """Reopen a closed ticket, preserving priority and history. Supply a reason."""
        return store.change(ticket_no, 'reopened', {'status': 'open'},
                            {'reason': clean(reason, 'Reason')}, require_closed=True)

    @expose('tickets', True)
    def ticket_history(ticket_no: int) -> dict:
        """Get chronological events and comments for an existing ticket."""
        return store.history(ticket_no)

    @expose('tickets', True)
    def ticket_stats() -> dict:
        """Count tickets by status and priority."""
        return store.stats()

    @expose('admin')
    def admin_delete_ticket(ticket_no: int, confirm: bool = False) -> dict:
        """Permanently delete a ticket and its history. Requires confirm=true. Prefer closing."""
        return store.delete(ticket_no, confirm)

    @expose('extras', True)
    def demo_weather(city: str) -> dict:
        """EXTRA DEMO: Return fictional weather, not live weather. Unrelated to ticket support."""
        return {'demo': True, 'city': city, 'temperature_c': 27, 'condition': 'sunny'}

    @expose('extras', True)
    def demo_currency_convert(amount: float, currency: Literal['USD', 'EUR']) -> dict:
        """EXTRA DEMO: Convert an amount to INR using fictional fixed rates, not live pricing."""
        return {'demo': True, 'amount_inr': round(amount * {'USD': 80, 'EUR': 90}[currency], 2)}

    @expose('extras', True)
    def demo_inventory_lookup(product_name: str) -> dict:
        """EXTRA DEMO: Return fictional stock for a product; not connected to order or ticket data."""
        return {'demo': True, 'product_name': product_name, 'stock': 25}

    @expose('extras', True)
    def demo_shipping_quote(weight_kg: float) -> dict:
        """EXTRA DEMO: Return a fictional shipping quote in INR for nonnegative weight."""
        if weight_kg < 0:
            raise ValueError('Weight cannot be negative')
        return {'demo': True, 'quote_inr': round(40 + weight_kg * 20, 2)}

    return mcp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    parser.add_argument('--profile', choices=PROFILES, default='all')
    parser.add_argument('--transport', choices=['stdio', 'http'], default='stdio')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    server = build_server(args.db, args.profile)
    # Stdout belongs to the MCP protocol: never print application logs here.
    if args.transport == 'http':
        server.run(transport='http', host='127.0.0.1', port=args.port, show_banner=False, log_level='ERROR')
    else:
        server.run(transport='stdio', show_banner=False, log_level='ERROR')


if __name__ == '__main__':
    main()
