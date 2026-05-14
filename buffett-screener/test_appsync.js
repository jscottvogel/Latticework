const query = `
query GetEverything {
  listWeeklyRuns { items { runId status runDate } }
  listStockScores { items { runId ticker compositeScore } }
  listRollingScores { items { ticker avgCompositeScore } }
}
`;

fetch("https://dggugtdqmbcilk5mk43axb2ixy.appsync-api.us-east-1.amazonaws.com/graphql", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "x-api-key": "da2-vgyu7lqg2vcbbm2w5etpxf2psy"
  },
  body: JSON.stringify({ query })
}).then(res => res.json()).then(data => console.log(JSON.stringify(data, null, 2))).catch(console.error);
