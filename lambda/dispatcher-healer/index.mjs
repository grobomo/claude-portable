/**
 * Dispatcher Auto-Healer Lambda
 *
 * Triggered by SNS when the dispatcher heartbeat CloudWatch alarm fires.
 * Checks the dispatcher EC2 instance state and:
 *   - Starts it if stopped
 *   - Launches a new one from the launch template if terminated/missing
 *
 * Environment variables:
 *   DISPATCHER_NAME         - Name tag of the dispatcher instance (default: claude-dispatcher)
 *   LAUNCH_TEMPLATE_NAME    - EC2 launch template name (default: claude-dispatcher-lt)
 *   AWS_REGION              - AWS region (default: us-east-2)
 */

import {
  EC2Client,
  DescribeInstancesCommand,
  StartInstancesCommand,
  RunInstancesCommand,
  DescribeLaunchTemplatesCommand,
} from '@aws-sdk/client-ec2';

const REGION = process.env.AWS_REGION || 'us-east-2';
const DISPATCHER_NAME = process.env.DISPATCHER_NAME || 'claude-dispatcher';
const LAUNCH_TEMPLATE_NAME = process.env.LAUNCH_TEMPLATE_NAME || 'claude-dispatcher-lt';

const ec2 = new EC2Client({ region: REGION });

/** Find dispatcher EC2 instances (any state). */
async function findDispatcherInstances() {
  const res = await ec2.send(new DescribeInstancesCommand({
    Filters: [
      { Name: 'tag:Project', Values: ['claude-portable'] },
      { Name: 'tag:Role',    Values: ['dispatcher'] },
      { Name: 'tag:Name',    Values: [DISPATCHER_NAME] },
    ],
  }));

  const instances = [];
  for (const r of (res.Reservations || [])) {
    for (const i of (r.Instances || [])) {
      instances.push({
        id:    i.InstanceId,
        state: i.State?.Name,
      });
    }
  }
  return instances;
}

/** Get the latest version of the launch template. */
async function getLaunchTemplateId() {
  const res = await ec2.send(new DescribeLaunchTemplatesCommand({
    Filters: [{ Name: 'launch-template-name', Values: [LAUNCH_TEMPLATE_NAME] }],
  }));
  const lt = (res.LaunchTemplates || [])[0];
  if (!lt) throw new Error(`Launch template not found: ${LAUNCH_TEMPLATE_NAME}`);
  return { id: lt.LaunchTemplateId, version: String(lt.LatestVersionNumber) };
}

/** Launch a fresh dispatcher instance from the existing launch template. */
async function launchDispatcher() {
  const { id, version } = await getLaunchTemplateId();
  console.log(`Launching new dispatcher from template ${id} v${version}`);
  const res = await ec2.send(new RunInstancesCommand({
    LaunchTemplate: { LaunchTemplateId: id, Version: version },
    MinCount: 1,
    MaxCount: 1,
  }));
  const newId = res.Instances?.[0]?.InstanceId;
  console.log(`Launched new dispatcher instance: ${newId}`);
  return newId;
}

export const handler = async (event) => {
  console.log('Event:', JSON.stringify(event, null, 2));

  // Parse SNS notification
  for (const record of (event.Records || [])) {
    let message;
    try {
      message = JSON.parse(record.Sns?.Message || '{}');
    } catch {
      console.warn('Could not parse SNS message, skipping record');
      continue;
    }

    const alarmState = message.NewStateValue;
    const alarmName  = message.AlarmName;
    console.log(`Alarm: ${alarmName}, State: ${alarmState}`);

    // Only act on ALARM state -- OKActions also send to this topic
    if (alarmState !== 'ALARM') {
      console.log('State is not ALARM, nothing to do.');
      continue;
    }

    // Find the dispatcher instance
    const instances = await findDispatcherInstances();
    console.log('Found instances:', JSON.stringify(instances));

    // Active instance states that need no action
    const active = instances.filter(i => ['running', 'pending'].includes(i.state));
    if (active.length > 0) {
      // Instance is running/pending -- alarm may be a transient blip; log and skip.
      console.log(`Dispatcher appears active (${active[0].state}). Monitoring only.`);
      continue;
    }

    // Stopped instance -- just start it
    const stopped = instances.filter(i => i.state === 'stopped');
    if (stopped.length > 0) {
      const inst = stopped[0];
      console.log(`Starting stopped dispatcher: ${inst.id}`);
      await ec2.send(new StartInstancesCommand({ InstanceIds: [inst.id] }));
      console.log(`Start request sent for ${inst.id}`);
      continue;
    }

    // No usable instance (terminated, shutting-down, or never existed)
    console.log('No running or stopped dispatcher found -- launching new instance.');
    await launchDispatcher();
  }

  return { statusCode: 200, body: 'OK' };
};
