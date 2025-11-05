#!/bin/bash
set -e

source deploy-config.sh

echo "======================================"
echo "🔍 Database Explorer"
echo "======================================"
echo ""

# Get connection name
export CONNECTION_NAME=$(gcloud sql instances describe $DB_INSTANCE_NAME \
  --format='value(connectionName)')

# Kill any existing proxy
pkill -f cloud-sql-proxy 2>/dev/null || true
sleep 2

# Start Cloud SQL Proxy
echo "🔌 Starting Cloud SQL Proxy..."
./cloud-sql-proxy $CONNECTION_NAME &
PROXY_PID=$!
sleep 5

cleanup() {
  echo ""
  echo "🧹 Stopping proxy..."
  kill $PROXY_PID 2>/dev/null || true
}
trap cleanup EXIT

# Function to run query
run_query() {
  PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -U $DB_USER -d $DB_NAME "$@"
}

# Get list of tables
echo "📊 Available Tables:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

TABLES=$(run_query -t -c "
  SELECT 
    schemaname || '.' || tablename as table_name,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
  FROM pg_tables 
  WHERE schemaname = 'public'
  ORDER BY tablename;
")

echo "$TABLES" | nl

# Get array of table names
TABLE_ARRAY=($(run_query -t -c "
  SELECT tablename 
  FROM pg_tables 
  WHERE schemaname = 'public'
  ORDER BY tablename;
" | tr -d ' '))

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Interactive loop
while true; do
  echo ""
  echo "Options:"
  echo "  [1-${#TABLE_ARRAY[@]}] - View specific table"
  echo "  [a] - View ALL tables"
  echo "  [s] - Show table structures"
  echo "  [c] - Show row counts"
  echo "  [q] - Quit"
  echo ""
  read -p "Enter your choice: " choice
  
  case $choice in
    [0-9]*)
      # View specific table
      if [ "$choice" -ge 1 ] && [ "$choice" -le "${#TABLE_ARRAY[@]}" ]; then
        TABLE_NAME=${TABLE_ARRAY[$((choice-1))]}
        echo ""
        echo "═══════════════════════════════════════"
        echo "📋 Table: $TABLE_NAME"
        echo "═══════════════════════════════════════"
        
        # Show count
        COUNT=$(run_query -t -c "SELECT COUNT(*) FROM $TABLE_NAME;")
        echo "Total rows: $COUNT"
        echo ""
        
        # Show structure
        echo "─── Structure ───"
        run_query -c "\d+ $TABLE_NAME"
        echo ""
        
        # Ask for limit
        read -p "How many rows to display? (default: 10, 'all' for all): " limit
        if [ -z "$limit" ]; then
          limit=10
        fi
        
        echo ""
        echo "─── Data ───"
        if [ "$limit" = "all" ]; then
          run_query -c "SELECT * FROM $TABLE_NAME;"
        else
          run_query -c "SELECT * FROM $TABLE_NAME LIMIT $limit;"
        fi
        
      else
        echo "❌ Invalid table number"
      fi
      ;;
      
    a|A)
      # View all tables
      echo ""
      echo "═══════════════════════════════════════"
      echo "📊 ALL TABLES"
      echo "═══════════════════════════════════════"
      
      read -p "How many rows per table? (default: 5): " limit
      if [ -z "$limit" ]; then
        limit=5
      fi
      
      for table in "${TABLE_ARRAY[@]}"; do
        echo ""
        echo "━━━ $table ━━━"
        COUNT=$(run_query -t -c "SELECT COUNT(*) FROM $table;")
        echo "Rows: $COUNT"
        run_query -c "SELECT * FROM $table LIMIT $limit;"
      done
      ;;
      
    s|S)
      # Show structures
      echo ""
      echo "═══════════════════════════════════════"
      echo "🏗️  TABLE STRUCTURES"
      echo "═══════════════════════════════════════"
      
      for table in "${TABLE_ARRAY[@]}"; do
        echo ""
        echo "━━━ $table ━━━"
        run_query -c "\d+ $table"
      done
      ;;
      
    c|C)
      # Show counts
      echo ""
      echo "═══════════════════════════════════════"
      echo "📊 ROW COUNTS"
      echo "═══════════════════════════════════════"
      echo ""
      
      for table in "${TABLE_ARRAY[@]}"; do
        COUNT=$(run_query -t -c "SELECT COUNT(*) FROM $table;" | tr -d ' ')
        printf "%-35s: %s\n" "$table" "$COUNT"
      done
      ;;
      
    q|Q)
      echo ""
      echo "👋 Goodbye!"
      exit 0
      ;;
      
    *)
      echo "❌ Invalid choice"
      ;;
  esac
done

