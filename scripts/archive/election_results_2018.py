import collections, requests, lxml, csv
from utils import load_data, save_data

# Open existing data.
legislators_historical = load_data("legislators-historical.yaml")
legislators_current = load_data("legislators-current.yaml")

# New member data.
party_map = { "R": "Republican", "D": "Democrat", "I": "Independent" }
office_building_map = { "RHOB": "Rayburn House Office Building", "CHOB": "Cannon House Office Building", "LHOB": "Longworth House Office Building" }
new_legislators = []

# Only class 1 senators were up for election. Mark all other
# senators as current.
elected = []
for p in legislators_current:
	if p["terms"][-1]["type"] == "sen" and p["terms"][-1]["class"] != 1:
		elected.append(p["id"]["bioguide"])
	if p["terms"][-1]["state"] == "PR":
		elected.append(p["id"]["bioguide"])

# Map bioguide and govtrack IDs to records.
bioguide = { }
for entry in legislators_historical + legislators_current:
	bioguide[entry['id']['bioguide']] = entry
govtrack = { }
for entry in legislators_historical + legislators_current:
	govtrack[entry['id']['govtrack']] = entry

# Get highest existing GovTrack ID to know where to start for assigning new IDs.
govtrack_id = max(p['id']['govtrack'] for p in (legislators_historical+legislators_current))

# Load members-elect data from the House Clerk.
xml = requests.get("http://clerk.house.gov/member_info/unofficial-116-member-elect-data.xml")
root = lxml.etree.fromstring(xml.content)
#root = lxml.etree.fromstring(open('unofficial-116-member-elect-data.xml', 'rb').read())
for node in root.findall('./members/member'):
	mi = node.find("member-info")

	# See if this is a legislator we know about.
	if mi.find("memindex") is None or not mi.find("memindex").text:
		print("No bioguide for", node.find("statdis").text, ": ", mi.find("footnote").text)
		continue
	bioguide_id = mi.find("memindex").text
	
	print(bioguide_id + "...")

	# Add to array markig this legislator as currently serving.
	elected.append(bioguide_id)

	# Don't add a new term for Puerto Rico's resident commissioner this election
	# because they're in the middle of a four-year term.
	if node.find("statdis").text[0:2] == "PR":
		continue

	if bioguide_id in bioguide:
		# Incumbent won or current representative has become a senator
		# or historical member is returning to office.
		p = bioguide[bioguide_id]

	else:
		# Make a new legislator entry.
		govtrack_id += 1
		p = collections.OrderedDict([
			("id", collections.OrderedDict([
				("bioguide", bioguide_id),
				#("fec", [row['fec']]),
				("govtrack", govtrack_id),
				#("opensecrets", None), # don't know yet
				#("votesmart", int(row['votesmart'])),
				#("wikipedia", row['wikipedia']),
				#("ballotpedia", row['ballotpedia']),
			])),
			("name", collections.OrderedDict([
				("first", mi.find('firstname').text),
				("middle", mi.find('middlename').text),
				("last", mi.find('lastname').text),
				#("official_full", mi.find('official-name').text), #not available yet
			])),
			("bio", collections.OrderedDict([
			 	("gender", "M" if mi.find('courtesy').text == "Mr." else "F"),
			 	#("birthday", row['birthday']),
			])),
			("terms", []),
		])
		if not p["name"]["middle"]:
			del p["name"]["middle"]
		new_legislators.append(p)

	# Add a new term.
	p['terms'].append(collections.OrderedDict([
		("type", "rep"),
		("start", "2019-01-03"),
		("end", "2021-01-03"),
		("state", mi.find('state').get('postal-code')), # the statedistrict node uses "AQ" for American Samoa but the state/@postal-code uses AS
		("district", int(node.find("statdis").text[2:])),
		("party", party_map[mi.find("party").text]),
		# caucus is unnecessary because there are currently no independents
		("phone", mi.find("phone").text),
		("address", mi.find("office-room").text + " " + office_building_map[mi.find("office-building").text] + " Washington DC " + mi.find("office-zip").text + "-" + mi.find("office-zip-suffix").text),
		("office", mi.find("office-room").text + " " + office_building_map[mi.find("office-building").text]),
	]))

	if len(p['terms']) > 1 and p["terms"][-2]["type"] == p["terms"][-1]["type"]:
		# This is an incumbent (or at least served in the same chamber previously).
		# Copy some fields forward that are likely to remain the same.
		for k in ('url', 'rss_url'):
			if k in p['terms'][-2]:
				p['terms'][-1][k] = p['terms'][-2][k]
			
# Load spreadsheet of Senate election results.
senators = csv.DictReader(open("archive/election_results_2018_senate.csv"))
for row in senators:
	if row['Incumbent Party'] == "": continue # the end
	if row['GovTrack ID'] and int(row['GovTrack ID']) in govtrack:
		# Incumbent won or current representative has become a senator
		# or historical member is returning to office.
		p = govtrack[int(row['GovTrack ID'])]

	else:
		# Make a new legislator entry.
		govtrack_id += 1
		p = collections.OrderedDict([
			("id", collections.OrderedDict([
				("bioguide", row['Bioguide ID']),
				("fec", [row['FEC.gov ID']]),
				("govtrack", govtrack_id),
				#("opensecrets", None), # don't know yet
				#("votesmart", int(row['votesmart'])),
				("wikipedia", row['Wikipedia Page Name']),
				("wikidata", row['Wikidata ID (see Wikipedia sidebar)']),
				("ballotpedia", row['Ballotpedia Page Name']),
			])),
			("name", collections.OrderedDict([
				("first", row['First Name']),
				("last", row['Last Name']),
				#("official_full", mi.find('official-name').text), #not available yet
			])),
			("bio", collections.OrderedDict([
			 	("gender", row['Gender (M/F)']),
			 	("birthday", row['Birthday (often on Wikipedia)']),
			])),
			("terms", []),
		])
		new_legislators.append(p)

	# Add to array markig this legislator as currently serving.
	elected.append(p['id']['bioguide'])

	# Add a new term.
	p['terms'].append(collections.OrderedDict([
		("type", "sen"),
		("start", "2019-01-03"),
		("end", "2025-01-03"),
		("state", row['State']),
		("class", 1),
		("party", row['Party'] or party_map[row['Incumbent Party']]), # incumbent party is listed differently than new legislator party
	]))
	if p['terms'][-1]['party'] == "Independent": # all independents current caucus with Dems
		p['terms'][-1]["caucus"] = "Democrat"
	p['terms'][-1]["state_rank"] = None # create a field so it's in the canonical order, but we'll assign below

	if len(p['terms']) > 1 and p["terms"][-2]["type"] == p["terms"][-1]["type"]:
		# This is an incumbent (or at least served in the same chamber previously).
		# Copy some fields forward that are likely to remain the same.
		for k in ('url', 'rss_url'):
			if k in p['terms'][-2]:
				p['terms'][-1][k] = p['terms'][-2][k]

# End any current leadership roles.
for p in legislators_current:
	for r in p.get('leadership_roles', []):
		if not r.get('end'):
			r['end'] = "2019-01-03"

# Split the legislators back into the historical and current list.
for p in legislators_current:
	if p["id"]["bioguide"] not in elected:
		legislators_historical.append(p)
legislators_current = [p for p in legislators_current if p['id']['bioguide'] in elected]
for p in legislators_historical:
	if p["id"]["bioguide"] in elected:
		legislators_current.append(p)
legislators_historical = [p for p in legislators_historical if p['id']['bioguide'] not in elected]
for p in new_legislators:
	legislators_current.append(p)

# Reset all state_rank entries. Since the legislators are roughly in seniority order,
# this will probably be right.
state_rank_assignment = set()
for p in legislators_current:
	if p['terms'][-1]['type'] == 'sen':
		if p['terms'][-1]['state'] not in state_rank_assignment:
			p['terms'][-1]['state_rank'] = 'senior'
			state_rank_assignment.add(p['terms'][-1]['state'])
		else:
			p['terms'][-1]['state_rank'] = 'junior'

# Save.
save_data(legislators_current, "legislators-current.yaml")
save_data(legislators_historical, "legislators-historical.yaml")

# Run the sweep script to clear out data that needs to be cleared out
# for legislators that are gone.
import sweep
sweep.run()
