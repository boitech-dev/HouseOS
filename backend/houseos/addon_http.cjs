// Narrow HTTPS transport: credential-bearing paths arrive over stdin, never argv/logs.
const https = require('node:https');
const net = require('node:net');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', value => { input += value; if (input.length > 16384) process.exit(1); });
process.stdin.on('end', () => {
  try {
    const {host, path, address, limit} = JSON.parse(input);
    if (typeof host !== 'string' || !/^[a-z0-9.-]{1,253}$/i.test(host) || !net.isIP(address) || typeof path !== 'string' || !path.startsWith('/') || /[\r\n]/.test(path) || !Number.isInteger(limit) || limit < 0 || limit > 4000000) throw Error();
    const req = https.get({hostname: host, path, timeout: 15000,
      lookup: (_, options, callback) => options.all ? callback(null, [{address, family: net.isIP(address)}]) : callback(null, address, net.isIP(address)),
      headers: {'Accept-Encoding': 'identity'}}, res => {
      if (res.statusCode !== 200) {
        process.stdout.write(JSON.stringify({status: res.statusCode, location: res.headers.location || ''}));res.destroy();return;
      }
      let bytes=0;const chunks=[];
      res.on('data', chunk => {bytes+=chunk.length;if(bytes>limit){res.destroy();process.exitCode=1;}else chunks.push(chunk);});
      res.on('end',()=>process.stdout.write(JSON.stringify({status:res.statusCode,body:Buffer.concat(chunks).toString('utf8')})));
      res.on('error',()=>{process.exitCode=1;});
    });
    req.on('timeout',()=>req.destroy());req.on('error',()=>{process.exitCode=1;});
  } catch { process.exitCode=1; }
});
